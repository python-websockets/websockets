from __future__ import annotations

import contextlib
import logging
import random
import socket
import struct
import threading
import uuid
from typing import Any, Dict, Iterable, Iterator, Mapping, Optional, Union, cast

from ..connection import Connection, Event, State
from ..exceptions import ConnectionClosed, ConnectionClosedOK, ProtocolError
from ..frames import DATA_OPCODES, BytesLike, Frame, Opcode, prepare_ctrl
from ..http11 import Request, Response
from ..typing import Data
from .messages import Assembler
from .utils import Deadline


__all__ = ["Protocol"]

logger = logging.getLogger(__name__)

BUFSIZE = 65536


class Protocol:
    """
    WebSocket connection.

    :class:`Protocol` provides APIs shared between WebSocket servers and
    clients. You shouldn't use it directly. Instead, use
    :class:`~websockets.sync.client.ClientProtocol` or
    :class:`~websockets.sync.server.ServerProtocol`.

    This documentation focuses on low-level details that aren't covered in the
    documentation of :class:`~websockets.sync.client.ClientProtocol` and
    :class:`~websockets.sync.server.ServerProtocol` for the sake of simplicity.

    The ``close_timeout`` parameter defines a maximum wait time for completing
    the closing handshake and terminating the TCP connection.

    Args:
        sock: network socket.
        connection: Sans-I/O connection.
        close_timeout: timeout for closing the connection in seconds.

    """

    def __init__(
        self,
        sock: socket.socket,
        connection: Connection,
        *,
        close_timeout: Optional[float] = None,
    ) -> None:
        self.sock = sock
        self.connection = connection
        self.close_timeout = close_timeout

        # Inject reference to this instance in the connection's logger.
        self.connection.logger = logging.LoggerAdapter(
            # https://github.com/python/typeshed/issues/5561
            cast(logging.Logger, self.connection.logger),
            {"websocket": self},
        )

        # Copy attributes from the connection for convenience.
        self.logger = self.connection.logger
        self.debug = self.connection.debug

        # HTTP handshake request and response.
        self.request: Optional[Request] = None
        self.response: Optional[Response] = None

        # Mutex serializing interactions with the connection.
        self.conn_mutex = threading.Lock()

        # Assembler turning frames into messages and serializing reads.
        self.recv_messages = Assembler()

        # Whether we are busy sending a fragmented message.
        self.send_in_progress = False

        # Mapping of ping IDs to pong waiters, in chronological order.
        self.pings: Dict[bytes, threading.Event] = {}

        # Receiving events from the socket.
        self.recv_events_thread = threading.Thread(target=self.recv_events)
        self.recv_events_thread.start()
        self.recv_events_exc: Optional[BaseException] = None

    # Public attributes

    @property
    def id(self) -> uuid.UUID:
        """
        Unique identifier of the connection. Useful in logs.

        """
        return self.connection.id

    @property
    def local_address(self) -> Any:
        """
        Local address of the connection.

        For IPv4 connections, this is a ``(host, port)`` tuple.

        The format of the address depends on the address family;
        see :meth:`~socket.socket.getsockname`.

        """
        return self.sock.getsockname()

    @property
    def remote_address(self) -> Any:
        """
        Remote address of the connection.

        For IPv4 connections, this is a ``(host, port)`` tuple.

        The format of the address depends on the address family;
        see :meth:`~socket.socket.getpeername`.

        """
        return self.sock.getpeername()

    # Public methods

    def __iter__(self) -> Iterator[Data]:
        """
        Iterate on incoming messages.

        The iterator exits normally when the connection is closed with the close
        code 1000 (OK) or 1001 (going away).

        It raises a :exc:`~websockets.exceptions.ConnectionClosedError`
        exception when the connection is closed with any other code.

        """
        try:
            while True:
                data = self.recv()
                assert data is not None, "recv without timeout cannot return None"
                yield data
        except ConnectionClosedOK:
            return

    def recv(self, timeout: Optional[float] = None) -> Data:
        """
        Receive the next message.

        When the connection is closed, :meth:`recv` raises
        :exc:`~websockets.exceptions.ConnectionClosed`. Specifically, it raises
        :exc:`~websockets.exceptions.ConnectionClosedOK` after a normal
        connection closure and
        :exc:`~websockets.exceptions.ConnectionClosedError` after a protocol
        error or a network failure. This is how you detect the end of the
        message stream.

        If ``timeout`` is ``None``, block until a message is received. If
        ``timeout`` is set and no message is received within ``timeout``
        seconds, raise :exc:`TimeoutError`. Set ``timeout`` to ``0`` to check if
        a message was already received.

        If the message is fragmented, wait until all fragments are received,
        reassemble them, and return the whole message.

        Returns:
            Data: A string (:class:`str`) for a Text_ frame. A bytestring
            (:class:`bytes`) for a Binary_ frame.

            .. _Text: https://www.rfc-editor.org/rfc/rfc6455.html#section-5.6
            .. _Binary: https://www.rfc-editor.org/rfc/rfc6455.html#section-5.6

        Raises:
            ConnectionClosed: when the connection is closed.
            RuntimeError: if two threads call :meth:`recv` or
                :meth:`recv_streaming` concurrently

        """
        try:
            return self.recv_messages.get(timeout)
        except EOFError:
            raise self.connection.close_exc from self.recv_events_exc
        except RuntimeError:
            raise RuntimeError(
                "cannot call recv() while another thread "
                "is already running recv() or recv_streaming()"
            )

    def recv_streaming(self) -> Iterator[Data]:
        """
        Receive the next message frame by frame.

        If the message is fragmented, yield each fragment as it is received.
        The iterator must be fully consumed, or else the connection will become
        unusable.

        With the exception of the return value, :meth:`recv_streaming` behaves
        like :meth:`recv`.

        Returns:
            Iterator[Data]: An iterator of strings (:class:`str`) for a Text_
                frame. An iterator of bytestrings (:class:`bytes`) for a
                Binary_ frame.

        Raises:
            ConnectionClosed: when the connection is closed.
            RuntimeError: if two threads call :meth:`recv` or
                :meth:`recv_streaming` concurrently

        """
        try:
            yield from self.recv_messages.get_iter()
        except EOFError:
            raise self.connection.close_exc from self.recv_events_exc
        except RuntimeError:
            raise RuntimeError(
                "cannot call recv_streaming() while another thread "
                "is already running recv() or recv_streaming()"
            )

    def send(self, message: Union[Data, Iterable[Data]]) -> None:
        """
        Send a message.

        A string (:class:`str`) is sent as a Text_ frame. A bytestring or
        bytes-like object (:class:`bytes`, :class:`bytearray`, or
        :class:`memoryview`) is sent as a Binary_ frame.

        .. _Text: https://www.rfc-editor.org/rfc/rfc6455.html#section-5.6
        .. _Binary: https://www.rfc-editor.org/rfc/rfc6455.html#section-5.6

        :meth:`send` also accepts an iterable of strings, bytestrings, or
        bytes-like objects to enable fragmentation_. Each item is treated as a
        message fragment and sent in its own frame. All items must be of the
        same type, or else :meth:`send` will raise a :exc:`TypeError` and the
        connection will be closed.

        .. _fragmentation: https://www.rfc-editor.org/rfc/rfc6455.html#section-5.4

        :meth:`send` rejects dict-like objects because this is often an error.
        (If you want to send the keys of a dict-like object as fragments, call
        its :meth:`~dict.keys` method and pass the result to :meth:`send`.)

        When the connection is closed, :meth:`send` raises
        :exc:`~websockets.exceptions.ConnectionClosed`. Specifically, it
        raises :exc:`~websockets.exceptions.ConnectionClosedOK` after a normal
        connection closure and
        :exc:`~websockets.exceptions.ConnectionClosedError` after a protocol
        error or a network failure.

        Args:
            message (Union[Data, Iterable[Data]): message to send.

        Raises:
            ConnectionClosed: when the connection is closed.
            RuntimeError: if a connection is busy sending a fragmented message.
            TypeError: if ``message`` doesn't have a supported type.

        """
        # Unfragmented message -- this case must be handled first because
        # strings and bytes-like objects are iterable.

        if isinstance(message, str):
            with self.send_context():
                if self.send_in_progress:
                    raise RuntimeError(
                        "cannot call send() while another thread "
                        "is already running send()"
                    )
                self.connection.send_text(message.encode("utf-8"))

        elif isinstance(message, BytesLike):
            with self.send_context():
                if self.send_in_progress:
                    raise RuntimeError(
                        "cannot call send() while another thread "
                        "is already running send()"
                    )
                self.connection.send_binary(message)

        # Catch a common mistake -- passing a dict to send().

        elif isinstance(message, Mapping):
            raise TypeError("data is a dict-like object")

        # Fragmented message -- regular iterator.

        elif isinstance(message, Iterable):
            chunks = iter(message)
            try:
                chunk = next(chunks)
            except StopIteration:
                return

            try:
                # First fragment.
                if isinstance(chunk, str):
                    text = True
                    with self.send_context():
                        if self.send_in_progress:
                            raise RuntimeError(
                                "cannot call send() while another thread "
                                "is already running send()"
                            )
                        self.send_in_progress = True
                        self.connection.send_text(
                            chunk.encode("utf-8"),
                            fin=False,
                        )
                elif isinstance(chunk, BytesLike):
                    text = False
                    with self.send_context():
                        if self.send_in_progress:
                            raise RuntimeError(
                                "cannot call send() while another thread "
                                "is already running send()"
                            )
                        self.send_in_progress = True
                        self.connection.send_binary(
                            chunk,
                            fin=False,
                        )
                else:
                    raise TypeError("data iterable must contain bytes or str")

                # Other fragments
                for chunk in chunks:
                    if isinstance(chunk, str) and text:
                        with self.send_context():
                            assert self.send_in_progress
                            self.connection.send_continuation(
                                chunk.encode("utf-8"),
                                fin=False,
                            )
                    elif isinstance(chunk, BytesLike) and not text:
                        with self.send_context():
                            assert self.send_in_progress
                            self.connection.send_continuation(
                                chunk,
                                fin=False,
                            )
                    else:
                        raise TypeError("data iterable must contain uniform types")

                # Final fragment.
                with self.send_context():
                    self.connection.send_continuation(b"", fin=True)
                    self.send_in_progress = False

            except Exception:
                # We're half-way through a fragmented message and we can't
                # complete it. This makes the connection unusable.
                with self.send_context(Deadline(self.close_timeout)):
                    self.connection.fail(1011, "error in fragmented message")
                raise

        else:
            raise TypeError("data must be bytes, str, or iterable")

    def close(self, code: int = 1000, reason: str = "") -> None:
        """
        Perform the closing handshake.

        :meth:`close` waits for the other end to complete the handshake and
        for the TCP connection to terminate.

        :meth:`close` is idempotent: it doesn't do anything once the
        connection is closed.

        Args:
            code: WebSocket close code.
            reason: WebSocket close reason.

        """
        try:
            with self.send_context(Deadline(self.close_timeout)):
                if self.send_in_progress:
                    self.connection.fail(1011, "close during fragmented message")
                else:
                    self.connection.send_close(code, reason)
        except ConnectionClosed:
            # Ignore ConnectionClosed exceptions raised from send_context().
            # They mean that the connection is closed, which was the goal.
            pass

    def ping(self, data: Optional[Data] = None) -> threading.Event:
        """
        Send a Ping_.

        .. _Ping: https://www.rfc-editor.org/rfc/rfc6455.html#section-5.5.2

        A ping may serve as a keepalive or as a check that the remote endpoint
        received all messages up to this point

        Args:
            data (Optional[Data]): payload of the ping; a string will be
                encoded to UTF-8; or :obj:`None` to generate a payload
                containing four random bytes.

        Returns:
            ~threading.Event: An event that will be set when the
            corresponding pong is received. You can ignore it if you
            don't intend to wait.

            ::

                pong_event = ws.ping()
                pong_event.wait()  # only if you want to wait for the pong

        Raises:
            ConnectionClosed: when the connection is closed.
            RuntimeError: if another ping was sent with the same data and
                the corresponding pong wasn't received yet.

        """
        if data is not None:
            data = prepare_ctrl(data)

        with self.send_context():
            # Protect against duplicates if a payload is explicitly set.
            if data in self.pings:
                raise RuntimeError("already waiting for a pong with the same data")

            # Generate a unique random payload otherwise.
            while data is None or data in self.pings:
                data = struct.pack("!I", random.getrandbits(32))

            self.pings[data] = threading.Event()
            self.connection.send_ping(data)
            return self.pings[data]

    def pong(self, data: Data = b"") -> None:
        """
        Send a Pong_.

        .. _Pong: https://www.rfc-editor.org/rfc/rfc6455.html#section-5.5.3

        An unsolicited pong may serve as a unidirectional heartbeat.

        Args:
            data (Data): payload of the pong; a string will be encoded to
                UTF-8.

        Raises:
            ConnectionClosed: when the connection is closed.

        """
        data = prepare_ctrl(data)

        with self.send_context():
            self.connection.send_pong(data)

    # Private methods

    def process_event(self, event: Event) -> None:
        """
        Process one incoming event.

        This method is overridden in subclasses to handle the handshake.

        """
        assert isinstance(event, Frame)
        if event.opcode in DATA_OPCODES:
            self.recv_messages.put(event)

        if event.opcode is Opcode.PING:
            self.acknowledge_pings(event.data)

    def acknowledge_pings(self, data: Data) -> None:
        """
        Acknowledge pings when receiving a pong.

        """
        with self.conn_mutex:
            # Ignore unsolicited pong.
            if data not in self.pings:
                return
            # Sending a pong for only the most recent ping is legal.
            # Acknowledge all previous pings too in that case.
            ping_id = None
            ping_ids = []
            for ping_id, ping in self.pings.items():
                ping_ids.append(ping_id)
                ping.set()
                if ping_id == data:
                    break
            else:  # pragma: no cover
                assert False, "solicited pong not found in pings"
            # Remove acknowledged pings from self.pings.
            for ping_id in ping_ids:
                del self.pings[ping_id]

    def recv_events(self) -> None:
        """
        Read incoming data from the socket and process events.

        Run this method in a thread as long as the connection is alive.

        ``recv_events()`` exits immediately when the ``self.sock`` is closed.

        """
        deadline: Optional[Deadline] = None
        try:
            while True:
                try:
                    if deadline is not None:
                        self.sock.settimeout(deadline.timeout())
                    data = self.sock.recv(BUFSIZE)
                except Exception as exc:
                    self.logger.debug("error while receiving data", exc_info=True)
                    self.recv_events_exc = exc
                    break

                # We reached EOF or we timed out during the closing handshake.
                if data == b"":
                    break

                # Acquire the connection lock.
                with self.conn_mutex:

                    # Feed incoming data to the connnection.
                    self.connection.receive_data(data)

                    # This isn't expected to raise an exception.
                    events = self.connection.events_received()

                    # Write outgoing data to the socket.
                    try:
                        self.send_data(deadline)
                    except Exception as exc:
                        self.logger.debug("error while sending data", exc_info=True)
                        self.recv_events_exc = exc
                        break

                    # Check if the connection is expected to close soon.
                    if self.connection.close_expected() and deadline is None:
                        deadline = Deadline(self.close_timeout)

                # Unlock conn_mutex before processing events. Else, the
                # application can't send messages in response to events.

                # If self.send_data() raised an exception, then events are lost.
                # This seems unlikely given that automatic responses write small
                # awounts of data.

                for event in events:
                    # This isn't expected to raise an exception.
                    self.process_event(event)

            # Breaking out of the while True: ... loop means that we believe
            # that the socket doesn't work anymore.
            with self.conn_mutex:

                # Feed the end of the data stream to the connnection.
                self.connection.receive_eof()

                # This isn't expected to generate events.
                assert not self.connection.events_received()

                # Write outgoing data to the socket.
                try:
                    self.send_data(deadline)
                except Exception as exc:
                    self.logger.debug("error while sending data", exc_info=True)
                    self.recv_events_exc = exc

        except Exception as exc:
            self.logger.error("unexpected internal error", exc_info=True)
            self.recv_events_exc = exc
        finally:
            # This isn't expected to raise an exception.
            self.recv_messages.close()
            self.sock.close()

    @contextlib.contextmanager
    def send_context(self, deadline: Optional[Deadline] = None, *, expected_state: State = State.OPEN) -> Iterator[None]:
        """
        Create a context for writing to the connection from user code.

        On entry, :meth:`send_context` acquires the connection lock and checks
        that the connection is open; on exit, it writes outgoing data to the
        socket::

            with self.send_context():
                self.connection.send_text(message.encode("utf-8"))

        When the connection isn't open on entry, when the connection is expected
        to close on exit, or when on unexpected error happens, terminating the
        connection, :meth:`send_context` waits until the connection is closed
        then raises :exc:`~websockets.exceptions.ConnectionClosed`.

        """
        # Should we wait until the connection is closed?
        wait_for_close = False
        # Should we raise ConnectionClosed?
        raise_close_exc = False
        original_exc: Optional[Exception] = None

        # Acquire the connection lock.
        with self.conn_mutex:

            if self.connection.state is expected_state:

                # Let the caller interact with the connection.
                try:
                    yield
                except (ProtocolError, RuntimeError):
                    # The connection state wasn't changed. Exit immediately.
                    raise
                except Exception as exc:
                    # We don't know what happened. Terminate the connection.
                    raise_close_exc = True
                    original_exc = exc
                else:

                    # Write outgoing data to the socket.
                    try:
                        self.send_data(deadline)
                    except Exception as exc:
                        self.logger.debug("error while sending data", exc_info=True)
                        # While the only expected exception here is OSError,
                        # other exceptions would be treated identically.
                        raise_close_exc = True
                        original_exc = exc
                    else:

                        # Check if the connection is expected to close soon.
                        wait_for_close = self.connection.close_expected()

            else:  # self.connection.state is not expected_state

                # Minor layering violation: we assume that the connection will
                # be closing soon if it isn't in the expected state.
                wait_for_close = True
                raise_close_exc = True

        # Release the connection lock by exiting the context manager before
        # waiting for recv_events() to terminate and to avoid a deadlock.

        # If the connection is expected to close soon and the close timeout
        # elapses, close the socket to terminate the connection.
        if wait_for_close:
            self.recv_events_thread.join(deadline.timeout())
            if self.recv_events_thread.is_alive():
                raise_close_exc = True
                # There's no risk to overwrite another error because
                # wait_for_close can be True only when no error occurred.
                assert original_exc is None
                original_exc = TimeoutError("timed out while closing connection")

        # If an error occurred, close the socket to terminate the connection and
        # raise an exception.
        if raise_close_exc:
            self.sock.close()
            self.recv_events_thread.join()
            raise self.connection.close_exc from original_exc

    def send_data(self, deadline: Optional[Deadline] = None) -> None:
        """
        Send outgoing data.

        Raises:
            OSError: when a socket operations fails.

        """
        assert self.conn_mutex.locked()
        for data in self.connection.data_to_send():
            if deadline is not None:
                self.sock.settimeout(deadline.timeout())
            if data:
                self.sock.sendall(data)
            else:
                self.sock.shutdown(socket.SHUT_WR)

    def wait_for_recv_events_thread(self, timeout: Optional[float] = None) -> None:
        """
        Wait for the thread running ``recv_events()`` to terminate.

        Raises:
            RuntimeError: when called from ``recv_events()``.

        """
        assert self.conn_mutex.locked()
        if self.recv_events_thread.is_alive():
            self.conn_mutex.release()
            self.recv_events_thread.join(timeout)
            self.conn_mutex.acquire()
