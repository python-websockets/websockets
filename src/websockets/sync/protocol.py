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

    The ``ping_interval`` and ``ping_timeout`` parameters aren't implemented
    yet.

    The ``close_timeout`` parameter defines a maximum wait time for completing
    the closing handshake and terminating the TCP connection.

    Args:
        sock: network socket.
        connection: Sans-I/O connection.
        ping_interval: delay between keepalive pings in seconds;
            :obj:`None` to disable keepalive pings.
        ping_timeout: timeout for keepalive pings in seconds;
            :obj:`None` to disable timeouts.
        close_timeout: timeout for closing the connection in seconds.

    """

    def __init__(
        self,
        sock: socket.socket,
        connection: Connection,
        ping_interval: Optional[float] = None,
        ping_timeout: Optional[float] = None,
        close_timeout: Optional[float] = None,
    ) -> None:
        self.sock = sock
        self.connection = connection
        if ping_interval is not None or ping_timeout is not None:  # pragma: no cover
            raise NotImplementedError("keepalive isn't implemented")
        self.close_timeout = close_timeout

        # Deadline created when the closing handshake starts.
        self.close_deadline: Optional[Deadline] = None

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
                with self.send_context():
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
            with self.send_context():
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
        try:
            while True:
                try:
                    data = self.sock.recv(BUFSIZE)
                except Exception as exc:
                    self.logger.debug("error while receiving data", exc_info=True)
                    self.recv_events_exc = exc
                    break

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
                        self.send_data()
                    except Exception as exc:
                        self.logger.debug("error while sending data", exc_info=True)
                        self.recv_events_exc = exc
                        break

                # Unlock conn_mutex before processing events. Else, the
                # application can't send messages in response to events.

                # If self.send_data() raised an exception, then events are lost.
                # This seems unlikely given that automatic responses write small
                # awounts of data.

                for event in events:
                    # This isn't expected to raise an exception.
                    self.process_event(event)

            # Breaking out of the while True: ... loop without an exception
            # means that we believe that the socket doesn't work anymore.
            with self.conn_mutex:

                # Feed the end of the data stream to the connnection.
                self.connection.receive_eof()

                # This isn't expected to generate events.
                assert not self.connection.events_received()

                # Write outgoing data to the socket.
                try:
                    self.send_data()
                except Exception as exc:
                    self.logger.debug("error while sending data", exc_info=True)
                    self.recv_events_exc = exc

        except Exception as exc:
            self.logger.error(
                "unexpected error while processing incoming data", exc_info=True
            )
            self.recv_events_exc = exc
        finally:
            # This isn't expected to raise an exception.
            self.recv_messages.close()
            self.sock.close()

    @contextlib.contextmanager
    def send_context(self, *, expected_state: State = State.OPEN) -> Iterator[None]:
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
                        self.send_data()
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
            self.recv_events_thread.join(self.close_timeout)
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

    def send_data(self) -> None:
        """
        Send outgoing data.

        Raises:
            OSError: when a socket operations fails.

        """
        assert self.conn_mutex.locked()
        for data in self.connection.data_to_send():
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


"""
.. currentmodule:: websockets

How many threads do we need?
----------------------------

1. One user thread
..................

We need at least one thread to execute the user's logic. For clients, this is
the thread that opens the connection. For servers, due to inversion of control,
this is the thread creatad by the server to handle the connection. Either way,
the user gets a :class:`~sync.protocol.Protocol` instance.

2. One library thread
.....................

Even if the user doesn't interact with the connection e.g. they don't receive
messages and they send messages infrequently, we still want to respond to pings.
Since we use blocking I/O, this requires a thread for reading from the network.

This thread runs ``recv_events()``. It exits if and only the socket is closed.
In other words, it must exit once the socket is closed for reading or writing
and it must close the socket for reading and writing before exiting.

3. No closing thread
....................

When the closing handshake is started, we want to enforce a close timeout, which
means closing the socket after 10 seconds by default if it isn't already closed.

There are two ways to achieve this:

1. When the closing hanshake is started, start a closing thread that waits for
   ``recv_events()`` to exit with a 10 seconds timeout. If the timeout elapses,
   the closing thread closes the socket. A separate thread is necessary because
   ``recv_events()`` can start the closing handshake but cannot wait for itself.
2. When the closing handshake is started from the user thread, in that thread,
   wait for ``recv_events()`` to exit with a 10 second timeout. When the closing
   handshake is started from the library thread, set a timeout on reading from
   the socket and close the socket if a read returns no data.

We choose option 2 because:

* Implementing two timeout mechanisms sounds less error-prone than coordinating
  three threads.
* Once the closing handshake is started, we want calls from the user thread to
  wait for the connection to be closed and return the correct exception so we
  need to handle the two cases differently anyway.

How do we handle concurrency?
-----------------------------

The user may run threads sharing access to the :class:`~sync.protocol.Protocol`
instance. We want websockets to be concurrency-safe.

For reading, attempting concurrent operations should raise :exc:`RuntimeError`.
Since reads can be slow, serialization could lead to misleading behavior e.g. it
isn't obvious whether a read is waiting for data or waiting for another read to
complete. This could hide deadlocks.

Also, concurrent reads are likely to be programming mistakes because they can
lead to non-deterministic behavior. Which read gets the next message? Multiple
consumers for incoming messages can be implemented by adding a queue.

For writing, attempting concurrent operations should result in serialization.
Since writes should be fast, serialization shouldn't to create issues. If it
leads to a deadlock, users will notice.

How many locks do we need?
--------------------------

1. Connection lock
..................

Both the user thread and the library thread may interact with the Sans-I/O
:class:`~connection.Connection` wrapped by the :class:`~sync.protocol.Protocol`.
This requires a mutex for serialization, ``conn_mutex``.

Critical sections protected with ``conn_mutex`` must include writing data to the
socket to guarantee that outgoing data is sent in the expected order.

Writing pings in the user thread and reading pongs in the library thread both
modify ``pings``. We reuse ``conn_mutex`` to protect access without creating a
risk of deadlocks.

2. No read lock
...............

The library thread reads incoming data from the socket, feeds it to the
:class:`~connection.Connection`, and pushes events to ``recv_messages``.

These actions happen sequentially in a single thread. Feeding data to the
:class:`~connection.Connection` is protected by the connection lock.
``recv_messages`` is thread-safe.

:meth:`~sync.protocol.Protocol.__iter__`, :meth:`~sync.protocol.Protocol.recv`,
and :meth:`~sync.protocol.Protocol.recv_streaming` are serialized by
``recv_messages.mutex``, which acts as the read lock.

(Calling :meth:`~sync.protocol.Protocol.recv` while
:meth:`~sync.protocol.Protocol.__iter__` is running isn't guaranteed to raise
:exc:`RuntimeError``. However, it will do so often enough for users to notice.)

3. No write lock
................

`:meth:`~sync.protocol.Protocol.send`, `:meth:`~sync.protocol.Protocol.close`,
`:meth:`~sync.protocol.Protocol.ping`, and `:meth:`~sync.protocol.Protocol.pong`
are sufficiently protected by ``conn_mutex``.

It is possible to hit a :exc:`RuntimeError`

can. This requires a mutex for serialization, ``send_mutex``.

Specifically, the write lock must ensure that data is sent to the network in the
same order

We cannot reuse ``conn_mutex`` becase ``close()`` must release it to let the
closing handshake complete, but it should still hold the write lock.

It might be possible to use the same lock for reads and writes, however that
wouldn't bring significant benefits.

How do we prevent deadlocks?
----------------------------

It is allowed to take locks in the following order:

* ``conn_mutex``
* ``messages.mutex``
* ``send_mutex``
    * ``conn_mutex``
    * ``pings_mutex``
* ``ping_mutex``

This prevents cycles and therefore deadlocks.

``recv_messages`` enforces synchronization between the library thread and the
user thread reading messages with a pair of events that make it behave like a
queue with a maximum size of one message. Serialization ensures that no more
than one thread can wait on these events, which makes deadlocks impossible.






Handling connection termination
-------------------------------




How do we handle connection errors?
-----------------------------------

In ``sock.recv()``
..................

``sock.recv()`` may raise ``OSError``. (See socketmodule.c.) All errors codes
listed in ``man 2 recv`` that may happen in the context of an established TCP
connection and that aren't handled automatically by Python (EINTR) signal that
the connection is closed or unresponsive:

* EAGAIN, EWOULDBLOCK (Linux): the connection is unresponsive; this happens only
  when a timeout is set on the socket i.e. during the closing handshake.
* EBADF, ECONNREFUSED (Linux), ECONNRESET (BSD): the connection is closed.

From the perspective of the WebSocket connection, this means that no more data
will be received, perhaps because we aren't going to wait for it. It doesn't
matter whether the TCP connection was closed properly. We signal this to the
Sans-I/O layer with ``receive_eof()``.

The ``OSError`` is captured in ``recv_events_exc`` and chained to
``ConnectionClosedError`` in ``recv()``, ``recv_streaming()``, and
``ensure_open()``.

In ``sock.sendall()`` and ``sock.shutwdown()``
..............................................

Similarly, ``sock.sendall()`` and ``sock.shutwdown()`` may raise ``OSError``,
meaning that the connection is unresponsive or closed.

From the perspective of the WebSocket connection, this means that no more data
can be sent. While reading could still be possible in theory...












                    # The TCP connection should be closed first by the server.
                    See 7.1.7 # of RFC 6455. Therefore, the following sequence
                    is expected.

                    # 1. The server starts the TCP closing handshake with a FIN
                    packet. #    This happens when data_to_send() signals EOF
                    with an empty #    bytestring, triggering
                    sock.shutdown(SHUT_WR).

                    # 2. The client reads until EOF and completes the TCP
                    closing #    handshake with a FIN packet. Again, this
                    happens when #    data_to_send() signals EOF with an empty
                    bytestring, triggering #    sock.shutdown(SHUT_WR). Then,
                    recv_events() terminates and #    calls sock.close().

                    # 3. The server reads until reaching EOF. recv_events()
                    terminates #    and calls sock.close(). This doesn't send a
                    packet.




                    except OSError as exc:  # sendall() or shutdown() failed
                        original_exc = exc self.logger.debug("error while
                        sending data", exc_info=True)
                    except Exception as exc:
                        original_exc = exc self.logger.error("unexpected error
                        while sending data", exc_info=True)




"""
