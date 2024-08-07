from __future__ import annotations

import asyncio
import collections
import contextlib
import logging
import random
import struct
import uuid
from types import TracebackType
from typing import (
    Any,
    AsyncIterable,
    AsyncIterator,
    Awaitable,
    Iterable,
    Mapping,
    cast,
)

from ..exceptions import ConnectionClosed, ConnectionClosedOK, ProtocolError
from ..frames import DATA_OPCODES, BytesLike, CloseCode, Frame, Opcode, prepare_ctrl
from ..http11 import Request, Response
from ..protocol import CLOSED, OPEN, Event, Protocol, State
from ..typing import Data, LoggerLike, Subprotocol
from .compatibility import TimeoutError, aiter, anext, asyncio_timeout_at
from .messages import Assembler


__all__ = ["Connection"]


class Connection(asyncio.Protocol):
    """
    :mod:`asyncio` implementation of a WebSocket connection.

    :class:`Connection` provides APIs shared between WebSocket servers and
    clients.

    You shouldn't use it directly. Instead, use
    :class:`~websockets.asyncio.client.ClientConnection` or
    :class:`~websockets.asyncio.server.ServerConnection`.

    """

    def __init__(
        self,
        protocol: Protocol,
        *,
        close_timeout: float | None = 10,
    ) -> None:
        self.protocol = protocol
        self.close_timeout = close_timeout

        # Inject reference to this instance in the protocol's logger.
        self.protocol.logger = logging.LoggerAdapter(
            self.protocol.logger,
            {"websocket": self},
        )

        # Copy attributes from the protocol for convenience.
        self.id: uuid.UUID = self.protocol.id
        """Unique identifier of the connection. Useful in logs."""
        self.logger: LoggerLike = self.protocol.logger
        """Logger for this connection."""
        self.debug = self.protocol.debug

        # HTTP handshake request and response.
        self.request: Request | None = None
        """Opening handshake request."""
        self.response: Response | None = None
        """Opening handshake response."""

        # Event loop running this connection.
        self.loop = asyncio.get_running_loop()

        # Assembler turning frames into messages and serializing reads.
        self.recv_messages: Assembler  # initialized in connection_made

        # Deadline for the closing handshake.
        self.close_deadline: float | None = None

        # Protect sending fragmented messages.
        self.fragmented_send_waiter: asyncio.Future[None] | None = None

        # Mapping of ping IDs to pong waiters, in chronological order.
        self.pong_waiters: dict[bytes, tuple[asyncio.Future[float], float]] = {}

        # Exception raised while reading from the connection, to be chained to
        # ConnectionClosed in order to show why the TCP connection dropped.
        self.recv_exc: BaseException | None = None

        # Completed when the TCP connection is closed and the WebSocket
        # connection state becomes CLOSED.
        self.connection_lost_waiter: asyncio.Future[None] = self.loop.create_future()

        # Adapted from asyncio.FlowControlMixin
        self.paused: bool = False
        self.drain_waiters: collections.deque[asyncio.Future[None]] = (
            collections.deque()
        )

    # Public attributes

    @property
    def local_address(self) -> Any:
        """
        Local address of the connection.

        For IPv4 connections, this is a ``(host, port)`` tuple.

        The format of the address depends on the address family.
        See :meth:`~socket.socket.getsockname`.

        """
        return self.transport.get_extra_info("sockname")

    @property
    def remote_address(self) -> Any:
        """
        Remote address of the connection.

        For IPv4 connections, this is a ``(host, port)`` tuple.

        The format of the address depends on the address family.
        See :meth:`~socket.socket.getpeername`.

        """
        return self.transport.get_extra_info("peername")

    @property
    def subprotocol(self) -> Subprotocol | None:
        """
        Subprotocol negotiated during the opening handshake.

        :obj:`None` if no subprotocol was negotiated.

        """
        return self.protocol.subprotocol

    # Public methods

    async def __aenter__(self) -> Connection:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if exc_type is None:
            await self.close()
        else:
            await self.close(CloseCode.INTERNAL_ERROR)

    async def __aiter__(self) -> AsyncIterator[Data]:
        """
        Iterate on incoming messages.

        The iterator calls :meth:`recv` and yields messages asynchronously in an
        infinite loop.

        It exits when the connection is closed normally. It raises a
        :exc:`~websockets.exceptions.ConnectionClosedError` exception after a
        protocol error or a network failure.

        """
        try:
            while True:
                yield await self.recv()
        except ConnectionClosedOK:
            return

    async def recv(self, decode: bool | None = None) -> Data:
        """
        Receive the next message.

        When the connection is closed, :meth:`recv` raises
        :exc:`~websockets.exceptions.ConnectionClosed`. Specifically, it raises
        :exc:`~websockets.exceptions.ConnectionClosedOK` after a normal closure
        and :exc:`~websockets.exceptions.ConnectionClosedError` after a protocol
        error or a network failure. This is how you detect the end of the
        message stream.

        Canceling :meth:`recv` is safe. There's no risk of losing data. The next
        invocation of :meth:`recv` will return the next message.

        This makes it possible to enforce a timeout by wrapping :meth:`recv` in
        :func:`~asyncio.timeout` or :func:`~asyncio.wait_for`.

        When the message is fragmented, :meth:`recv` waits until all fragments
        are received, reassembles them, and returns the whole message.

        Args:
            decode: Set this flag to override the default behavior of returning
                :class:`str` or :class:`bytes`. See below for details.

        Returns:
            A string (:class:`str`) for a Text_ frame or a bytestring
            (:class:`bytes`) for a Binary_ frame.

            .. _Text: https://www.rfc-editor.org/rfc/rfc6455.html#section-5.6
            .. _Binary: https://www.rfc-editor.org/rfc/rfc6455.html#section-5.6

            You may override this behavior with the ``decode`` argument:

            * Set ``decode=False`` to disable UTF-8 decoding of Text_ frames
              and return a bytestring (:class:`bytes`). This may be useful to
              optimize performance when decoding isn't needed.
            * Set ``decode=True`` to force UTF-8 decoding of Binary_ frames
              and return a string (:class:`str`). This is useful for servers
              that send binary frames instead of text frames.

        Raises:
            ConnectionClosed: When the connection is closed.
            RuntimeError: If two coroutines call :meth:`recv` or
                :meth:`recv_streaming` concurrently.

        """
        try:
            return await self.recv_messages.get(decode)
        except EOFError:
            raise self.protocol.close_exc from self.recv_exc
        except RuntimeError:
            raise RuntimeError(
                "cannot call recv while another coroutine "
                "is already running recv or recv_streaming"
            ) from None

    async def recv_streaming(self, decode: bool | None = None) -> AsyncIterator[Data]:
        """
        Receive the next message frame by frame.

        This method is designed for receiving fragmented messages. It returns an
        asynchronous iterator that yields each fragment as it is received. This
        iterator must be fully consumed. Else, future calls to :meth:`recv` or
        :meth:`recv_streaming` will raise :exc:`RuntimeError`, making the
        connection unusable.

        :meth:`recv_streaming` raises the same exceptions as :meth:`recv`.

        Canceling :meth:`recv_streaming` before receiving the first frame is
        safe. Canceling it after receiving one or more frames leaves the
        iterator in a partially consumed state, making the connection unusable.
        Instead, you should close the connection with :meth:`close`.

        Args:
            decode: Set this flag to override the default behavior of returning
                :class:`str` or :class:`bytes`. See below for details.

        Returns:
            An iterator of strings (:class:`str`) for a Text_ frame or
            bytestrings (:class:`bytes`) for a Binary_ frame.

            .. _Text: https://www.rfc-editor.org/rfc/rfc6455.html#section-5.6
            .. _Binary: https://www.rfc-editor.org/rfc/rfc6455.html#section-5.6

            You may override this behavior with the ``decode`` argument:

            * Set ``decode=False`` to disable UTF-8 decoding of Text_ frames
              and return bytestrings (:class:`bytes`). This may be useful to
              optimize performance when decoding isn't needed.
            * Set ``decode=True`` to force UTF-8 decoding of Binary_ frames
              and return strings (:class:`str`). This is useful for servers
              that send binary frames instead of text frames.

        Raises:
            ConnectionClosed: When the connection is closed.
            RuntimeError: If two coroutines call :meth:`recv` or
                :meth:`recv_streaming` concurrently.

        """
        try:
            async for frame in self.recv_messages.get_iter(decode):
                yield frame
        except EOFError:
            raise self.protocol.close_exc from self.recv_exc
        except RuntimeError:
            raise RuntimeError(
                "cannot call recv_streaming while another coroutine "
                "is already running recv or recv_streaming"
            ) from None

    async def send(self, message: Data | Iterable[Data] | AsyncIterable[Data]) -> None:
        """
        Send a message.

        A string (:class:`str`) is sent as a Text_ frame. A bytestring or
        bytes-like object (:class:`bytes`, :class:`bytearray`, or
        :class:`memoryview`) is sent as a Binary_ frame.

        .. _Text: https://www.rfc-editor.org/rfc/rfc6455.html#section-5.6
        .. _Binary: https://www.rfc-editor.org/rfc/rfc6455.html#section-5.6

        :meth:`send` also accepts an iterable or an asynchronous iterable of
        strings, bytestrings, or bytes-like objects to enable fragmentation_.
        Each item is treated as a message fragment and sent in its own frame.
        All items must be of the same type, or else :meth:`send` will raise a
        :exc:`TypeError` and the connection will be closed.

        .. _fragmentation: https://www.rfc-editor.org/rfc/rfc6455.html#section-5.4

        :meth:`send` rejects dict-like objects because this is often an error.
        (If you really want to send the keys of a dict-like object as fragments,
        call its :meth:`~dict.keys` method and pass the result to :meth:`send`.)

        Canceling :meth:`send` is discouraged. Instead, you should close the
        connection with :meth:`close`. Indeed, there are only two situations
        where :meth:`send` may yield control to the event loop and then get
        canceled; in both cases, :meth:`close` has the same effect and is
        more clear:

        1. The write buffer is full. If you don't want to wait until enough
           data is sent, your only alternative is to close the connection.
           :meth:`close` will likely time out then abort the TCP connection.
        2. ``message`` is an asynchronous iterator that yields control.
           Stopping in the middle of a fragmented message will cause a
           protocol error and the connection will be closed.

        When the connection is closed, :meth:`send` raises
        :exc:`~websockets.exceptions.ConnectionClosed`. Specifically, it
        raises :exc:`~websockets.exceptions.ConnectionClosedOK` after a normal
        connection closure and
        :exc:`~websockets.exceptions.ConnectionClosedError` after a protocol
        error or a network failure.

        Args:
            message: Message to send.

        Raises:
            ConnectionClosed: When the connection is closed.
            RuntimeError: If the connection busy sending a fragmented message.
            TypeError: If ``message`` doesn't have a supported type.

        """
        # While sending a fragmented message, prevent sending other messages
        # until all fragments are sent.
        while self.fragmented_send_waiter is not None:
            await asyncio.shield(self.fragmented_send_waiter)

        # Unfragmented message -- this case must be handled first because
        # strings and bytes-like objects are iterable.

        if isinstance(message, str):
            async with self.send_context():
                self.protocol.send_text(message.encode())

        elif isinstance(message, BytesLike):
            async with self.send_context():
                self.protocol.send_binary(message)

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

            assert self.fragmented_send_waiter is None
            self.fragmented_send_waiter = self.loop.create_future()
            try:
                # First fragment.
                if isinstance(chunk, str):
                    text = True
                    async with self.send_context():
                        self.protocol.send_text(
                            chunk.encode(),
                            fin=False,
                        )
                elif isinstance(chunk, BytesLike):
                    text = False
                    async with self.send_context():
                        self.protocol.send_binary(
                            chunk,
                            fin=False,
                        )
                else:
                    raise TypeError("iterable must contain bytes or str")

                # Other fragments
                for chunk in chunks:
                    if isinstance(chunk, str) and text:
                        async with self.send_context():
                            self.protocol.send_continuation(
                                chunk.encode(),
                                fin=False,
                            )
                    elif isinstance(chunk, BytesLike) and not text:
                        async with self.send_context():
                            self.protocol.send_continuation(
                                chunk,
                                fin=False,
                            )
                    else:
                        raise TypeError("iterable must contain uniform types")

                # Final fragment.
                async with self.send_context():
                    self.protocol.send_continuation(b"", fin=True)

            except Exception:
                # We're half-way through a fragmented message and we can't
                # complete it. This makes the connection unusable.
                async with self.send_context():
                    self.protocol.fail(1011, "error in fragmented message")
                raise

            finally:
                self.fragmented_send_waiter.set_result(None)
                self.fragmented_send_waiter = None

        # Fragmented message -- async iterator.

        elif isinstance(message, AsyncIterable):
            achunks = aiter(message)
            try:
                chunk = await anext(achunks)
            except StopAsyncIteration:
                return

            assert self.fragmented_send_waiter is None
            self.fragmented_send_waiter = self.loop.create_future()
            try:
                # First fragment.
                if isinstance(chunk, str):
                    text = True
                    async with self.send_context():
                        self.protocol.send_text(
                            chunk.encode(),
                            fin=False,
                        )
                elif isinstance(chunk, BytesLike):
                    text = False
                    async with self.send_context():
                        self.protocol.send_binary(
                            chunk,
                            fin=False,
                        )
                else:
                    raise TypeError("async iterable must contain bytes or str")

                # Other fragments
                async for chunk in achunks:
                    if isinstance(chunk, str) and text:
                        async with self.send_context():
                            self.protocol.send_continuation(
                                chunk.encode(),
                                fin=False,
                            )
                    elif isinstance(chunk, BytesLike) and not text:
                        async with self.send_context():
                            self.protocol.send_continuation(
                                chunk,
                                fin=False,
                            )
                    else:
                        raise TypeError("async iterable must contain uniform types")

                # Final fragment.
                async with self.send_context():
                    self.protocol.send_continuation(b"", fin=True)

            except Exception:
                # We're half-way through a fragmented message and we can't
                # complete it. This makes the connection unusable.
                async with self.send_context():
                    self.protocol.fail(1011, "error in fragmented message")
                raise

            finally:
                self.fragmented_send_waiter.set_result(None)
                self.fragmented_send_waiter = None

        else:
            raise TypeError("data must be bytes, str, iterable, or async iterable")

    async def close(self, code: int = 1000, reason: str = "") -> None:
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
            # The context manager takes care of waiting for the TCP connection
            # to terminate after calling a method that sends a close frame.
            async with self.send_context():
                if self.fragmented_send_waiter is not None:
                    self.protocol.fail(1011, "close during fragmented message")
                else:
                    self.protocol.send_close(code, reason)
        except ConnectionClosed:
            # Ignore ConnectionClosed exceptions raised from send_context().
            # They mean that the connection is closed, which was the goal.
            pass

    async def wait_closed(self) -> None:
        """
        Wait until the connection is closed.

        :meth:`wait_closed` waits for the closing handshake to complete and for
        the TCP connection to terminate.

        """
        await asyncio.shield(self.connection_lost_waiter)

    async def ping(self, data: Data | None = None) -> Awaitable[None]:
        """
        Send a Ping_.

        .. _Ping: https://www.rfc-editor.org/rfc/rfc6455.html#section-5.5.2

        A ping may serve as a keepalive or as a check that the remote endpoint
        received all messages up to this point

        Args:
            data: Payload of the ping. A :class:`str` will be encoded to UTF-8.
                If ``data`` is :obj:`None`, the payload is four random bytes.

        Returns:
            A future that will be completed when the corresponding pong is
            received. You can ignore it if you don't intend to wait. The result
            of the future is the latency of the connection in seconds.

            ::

                pong_waiter = await ws.ping()
                # only if you want to wait for the corresponding pong
                latency = await pong_waiter

        Raises:
            ConnectionClosed: When the connection is closed.
            RuntimeError: If another ping was sent with the same data and
                the corresponding pong wasn't received yet.

        """
        if data is not None:
            data = prepare_ctrl(data)

        async with self.send_context():
            # Protect against duplicates if a payload is explicitly set.
            if data in self.pong_waiters:
                raise RuntimeError("already waiting for a pong with the same data")

            # Generate a unique random payload otherwise.
            while data is None or data in self.pong_waiters:
                data = struct.pack("!I", random.getrandbits(32))

            pong_waiter = self.loop.create_future()
            # The event loop's default clock is time.monotonic(). Its resolution
            # is a bit low on Windows (~16ms). We cannot use time.perf_counter()
            # because it doesn't count time elapsed while the process sleeps.
            ping_timestamp = self.loop.time()
            self.pong_waiters[data] = (pong_waiter, ping_timestamp)
            self.protocol.send_ping(data)
            return pong_waiter

    async def pong(self, data: Data = b"") -> None:
        """
        Send a Pong_.

        .. _Pong: https://www.rfc-editor.org/rfc/rfc6455.html#section-5.5.3

        An unsolicited pong may serve as a unidirectional heartbeat.

        Args:
            data: Payload of the pong. A :class:`str` will be encoded to UTF-8.

        Raises:
            ConnectionClosed: When the connection is closed.

        """
        data = prepare_ctrl(data)

        async with self.send_context():
            self.protocol.send_pong(data)

    # Private methods

    def process_event(self, event: Event) -> None:
        """
        Process one incoming event.

        This method is overridden in subclasses to handle the handshake.

        """
        assert isinstance(event, Frame)
        if event.opcode in DATA_OPCODES:
            self.recv_messages.put(event)

        if event.opcode is Opcode.PONG:
            self.acknowledge_pings(bytes(event.data))

    def acknowledge_pings(self, data: bytes) -> None:
        """
        Acknowledge pings when receiving a pong.

        """
        # Ignore unsolicited pong.
        if data not in self.pong_waiters:
            return

        pong_timestamp = self.loop.time()

        # Sending a pong for only the most recent ping is legal.
        # Acknowledge all previous pings too in that case.
        ping_id = None
        ping_ids = []
        for ping_id, (pong_waiter, ping_timestamp) in self.pong_waiters.items():
            ping_ids.append(ping_id)
            pong_waiter.set_result(pong_timestamp - ping_timestamp)
            if ping_id == data:
                break
        else:
            raise AssertionError("solicited pong not found in pings")

        # Remove acknowledged pings from self.pong_waiters.
        for ping_id in ping_ids:
            del self.pong_waiters[ping_id]

    def abort_pings(self) -> None:
        """
        Raise ConnectionClosed in pending pings.

        They'll never receive a pong once the connection is closed.

        """
        assert self.protocol.state is CLOSED
        exc = self.protocol.close_exc

        for pong_waiter, _ping_timestamp in self.pong_waiters.values():
            pong_waiter.set_exception(exc)
            # If the exception is never retrieved, it will be logged when ping
            # is garbage-collected. This is confusing for users.
            # Given that ping is done (with an exception), canceling it does
            # nothing, but it prevents logging the exception.
            pong_waiter.cancel()

        self.pong_waiters.clear()

    @contextlib.asynccontextmanager
    async def send_context(
        self,
        *,
        expected_state: State = OPEN,  # CONNECTING during the opening handshake
    ) -> AsyncIterator[None]:
        """
        Create a context for writing to the connection from user code.

        On entry, :meth:`send_context` checks that the connection is open; on
        exit, it writes outgoing data to the socket::

            async async with self.send_context():
                self.protocol.send_text(message.encode())

        When the connection isn't open on entry, when the connection is expected
        to close on exit, or when an unexpected error happens, terminating the
        connection, :meth:`send_context` waits until the connection is closed
        then raises :exc:`~websockets.exceptions.ConnectionClosed`.

        """
        # Should we wait until the connection is closed?
        wait_for_close = False
        # Should we close the transport and raise ConnectionClosed?
        raise_close_exc = False
        # What exception should we chain ConnectionClosed to?
        original_exc: BaseException | None = None

        if self.protocol.state is expected_state:
            # Let the caller interact with the protocol.
            try:
                yield
            except (ProtocolError, RuntimeError):
                # The protocol state wasn't changed. Exit immediately.
                raise
            except Exception as exc:
                self.logger.error("unexpected internal error", exc_info=True)
                # This branch should never run. It's a safety net in case of
                # bugs. Since we don't know what happened, we will close the
                # connection and raise the exception to the caller.
                wait_for_close = False
                raise_close_exc = True
                original_exc = exc
            else:
                # Check if the connection is expected to close soon.
                if self.protocol.close_expected():
                    wait_for_close = True
                    # If the connection is expected to close soon, set the
                    # close deadline based on the close timeout.
                    # Since we tested earlier that protocol.state was OPEN
                    # (or CONNECTING), self.close_deadline is still None.
                    if self.close_timeout is not None:
                        assert self.close_deadline is None
                        self.close_deadline = self.loop.time() + self.close_timeout
                # Write outgoing data to the socket and enforce flow control.
                try:
                    self.send_data()
                    await self.drain()
                except Exception as exc:
                    if self.debug:
                        self.logger.debug("error while sending data", exc_info=True)
                    # While the only expected exception here is OSError,
                    # other exceptions would be treated identically.
                    wait_for_close = False
                    raise_close_exc = True
                    original_exc = exc

        else:  # self.protocol.state is not expected_state
            # Minor layering violation: we assume that the connection
            # will be closing soon if it isn't in the expected state.
            wait_for_close = True
            # Calculate close_deadline if it wasn't set yet.
            if self.close_timeout is not None:
                if self.close_deadline is None:
                    self.close_deadline = self.loop.time() + self.close_timeout
            raise_close_exc = True

        # If the connection is expected to close soon and the close timeout
        # elapses, close the socket to terminate the connection.
        if wait_for_close:
            try:
                async with asyncio_timeout_at(self.close_deadline):
                    await asyncio.shield(self.connection_lost_waiter)
            except TimeoutError:
                # There's no risk to overwrite another error because
                # original_exc is never set when wait_for_close is True.
                assert original_exc is None
                original_exc = TimeoutError("timed out while closing connection")
                # Set recv_exc before closing the transport in order to get
                # proper exception reporting.
                raise_close_exc = True
                self.set_recv_exc(original_exc)

        # If an error occurred, close the transport to terminate the connection and
        # raise an exception.
        if raise_close_exc:
            self.close_transport()
            await asyncio.shield(self.connection_lost_waiter)
            raise self.protocol.close_exc from original_exc

    def send_data(self) -> None:
        """
        Send outgoing data.

        Raises:
            OSError: When a socket operations fails.

        """
        for data in self.protocol.data_to_send():
            if data:
                self.transport.write(data)
            else:
                # Half-close the TCP connection when possible i.e. no TLS.
                if self.transport.can_write_eof():
                    if self.debug:
                        self.logger.debug("x half-closing TCP connection")
                    # write_eof() doesn't document which exceptions it raises.
                    # OSError is plausible. uvloop can raise RuntimeError here.
                    try:
                        self.transport.write_eof()
                    except (OSError, RuntimeError):  # pragma: no cover
                        pass
                # Else, close the TCP connection.
                else:  # pragma: no cover
                    if self.debug:
                        self.logger.debug("x closing TCP connection")
                    self.transport.close()

    def set_recv_exc(self, exc: BaseException | None) -> None:
        """
        Set recv_exc, if not set yet.

        """
        if self.recv_exc is None:
            self.recv_exc = exc

    def close_transport(self) -> None:
        """
        Close transport and message assembler.

        """
        self.transport.close()
        self.recv_messages.close()

    # asyncio.Protocol methods

    # Connection callbacks

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        transport = cast(asyncio.Transport, transport)
        self.transport = transport
        self.recv_messages = Assembler(
            pause=self.transport.pause_reading,
            resume=self.transport.resume_reading,
        )

    def connection_lost(self, exc: Exception | None) -> None:
        self.protocol.receive_eof()  # receive_eof is idempotent
        self.recv_messages.close()
        self.set_recv_exc(exc)
        # If self.connection_lost_waiter isn't pending, that's a bug, because:
        # - it's set only here in connection_lost() which is called only once;
        # - it must never be canceled.
        self.connection_lost_waiter.set_result(None)
        self.abort_pings()

        # Adapted from asyncio.streams.FlowControlMixin
        if self.paused:  # pragma: no cover
            self.paused = False
            for waiter in self.drain_waiters:
                if not waiter.done():
                    if exc is None:
                        waiter.set_result(None)
                    else:
                        waiter.set_exception(exc)

    # Flow control callbacks

    def pause_writing(self) -> None:  # pragma: no cover
        # Adapted from asyncio.streams.FlowControlMixin
        assert not self.paused
        self.paused = True

    def resume_writing(self) -> None:  # pragma: no cover
        # Adapted from asyncio.streams.FlowControlMixin
        assert self.paused
        self.paused = False
        for waiter in self.drain_waiters:
            if not waiter.done():
                waiter.set_result(None)

    async def drain(self) -> None:  # pragma: no cover
        # We don't check if the connection is closed because we call drain()
        # immediately after write() and write() would fail in that case.

        # Adapted from asyncio.streams.StreamWriter
        # Yield to the event loop so that connection_lost() may be called.
        if self.transport.is_closing():
            await asyncio.sleep(0)

        # Adapted from asyncio.streams.FlowControlMixin
        if self.paused:
            waiter = self.loop.create_future()
            self.drain_waiters.append(waiter)
            try:
                await waiter
            finally:
                self.drain_waiters.remove(waiter)

    # Streaming protocol callbacks

    def data_received(self, data: bytes) -> None:
        # Feed incoming data to the protocol.
        self.protocol.receive_data(data)

        # This isn't expected to raise an exception.
        events = self.protocol.events_received()

        # Write outgoing data to the transport.
        try:
            self.send_data()
        except Exception as exc:
            if self.debug:
                self.logger.debug("error while sending data", exc_info=True)
            self.set_recv_exc(exc)

        if self.protocol.close_expected():
            # If the connection is expected to close soon, set the
            # close deadline based on the close timeout.
            if self.close_timeout is not None:
                if self.close_deadline is None:
                    self.close_deadline = self.loop.time() + self.close_timeout

        for event in events:
            # This isn't expected to raise an exception.
            self.process_event(event)

    def eof_received(self) -> None:
        # Feed the end of the data stream to the connection.
        self.protocol.receive_eof()

        # This isn't expected to generate events.
        assert not self.protocol.events_received()

        # There is no error handling because send_data() can only write
        # the end of the data stream here and it shouldn't raise errors.
        self.send_data()

        # The WebSocket protocol has its own closing handshake: endpoints close
        # the TCP or TLS connection after sending and receiving a close frame.
        # As a consequence, they never need to write after receiving EOF, so
        # there's no reason to keep the transport open by returning True.
        # Besides, that doesn't work on TLS connections.
