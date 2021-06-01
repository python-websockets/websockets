"""
:mod:`websockets.legacy.protocol` handles WebSocket control and data frames.

See `sections 4 to 8 of RFC 6455`_.

.. _sections 4 to 8 of RFC 6455: http://tools.ietf.org/html/rfc6455#section-4

"""

import asyncio
import codecs
import collections
import enum
import logging
import random
import struct
import uuid
import warnings
from typing import (
    Any,
    AsyncIterable,
    AsyncIterator,
    Awaitable,
    Deque,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Union,
    cast,
)

from ..datastructures import Headers
from ..exceptions import (
    ConnectionClosed,
    ConnectionClosedError,
    ConnectionClosedOK,
    InvalidState,
    PayloadTooBig,
    ProtocolError,
)
from ..extensions.base import Extension
from ..frames import (
    OP_BINARY,
    OP_CLOSE,
    OP_CONT,
    OP_PING,
    OP_PONG,
    OP_TEXT,
    Opcode,
    parse_close,
    prepare_ctrl,
    prepare_data,
    serialize_close,
)
from ..typing import Data, LoggerLike, Subprotocol
from .compatibility import loop_if_py_lt_38
from .framing import Frame


__all__ = ["WebSocketCommonProtocol"]


# A WebSocket connection goes through the following four states, in order:


class State(enum.IntEnum):
    CONNECTING, OPEN, CLOSING, CLOSED = range(4)


# In order to ensure consistency, the code always checks the current value of
# WebSocketCommonProtocol.state before assigning a new value and never yields
# between the check and the assignment.


class WebSocketCommonProtocol(asyncio.Protocol):
    """
    :class:`~asyncio.Protocol` subclass implementing the data transfer phase.

    Once the WebSocket connection is established, during the data transfer
    phase, the protocol is almost symmetrical between the server side and the
    client side. :class:`WebSocketCommonProtocol` implements logic that's
    shared between servers and clients.

    Subclasses such as
    :class:`~websockets.legacy.server.WebSocketServerProtocol` and
    :class:`~websockets.legacy.client.WebSocketClientProtocol` implement the
    opening handshake, which is different between servers and clients.

    """

    # There are only two differences between the client-side and server-side
    # behavior: masking the payload and closing the underlying TCP connection.
    # Set is_client = True/False and side = "client"/"server" to pick a side.
    is_client: bool
    side: str = "undefined"

    def __init__(
        self,
        *,
        ping_interval: Optional[float] = 20,
        ping_timeout: Optional[float] = 20,
        close_timeout: Optional[float] = None,
        max_size: Optional[int] = 2 ** 20,
        max_queue: Optional[int] = 2 ** 5,
        read_limit: int = 2 ** 16,
        write_limit: int = 2 ** 16,
        logger: Optional[LoggerLike] = None,
        # The following arguments are kept only for backwards compatibility.
        host: Optional[str] = None,
        port: Optional[int] = None,
        secure: Optional[bool] = None,
        timeout: Optional[float] = None,
        legacy_recv: bool = False,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> None:
        # Backwards compatibility: close_timeout used to be called timeout.
        if timeout is None:
            timeout = 10
        else:
            warnings.warn("rename timeout to close_timeout", DeprecationWarning)
        # If both are specified, timeout is ignored.
        if close_timeout is None:
            close_timeout = timeout

        self.ping_interval = ping_interval
        self.ping_timeout = ping_timeout
        self.close_timeout = close_timeout
        self.max_size = max_size
        self.max_queue = max_queue
        self.read_limit = read_limit
        self.write_limit = write_limit

        # Unique identifier. For logs.
        self.id = uuid.uuid4()

        # Logger or LoggerAdapter for this connection.
        if logger is None:
            logger = logging.getLogger("websockets.protocol")
        # https://github.com/python/typeshed/issues/5561
        logger = cast(logging.Logger, logger)
        self.logger = logging.LoggerAdapter(logger, {"websocket": self})

        # Track if DEBUG is enabled. Shortcut logging calls if it isn't.
        self.debug = logger.isEnabledFor(logging.DEBUG)

        assert loop is not None
        # Remove when dropping Python < 3.10 - use get_running_loop instead.
        self.loop = loop

        self._host = host
        self._port = port
        self._secure = secure
        self.legacy_recv = legacy_recv

        # Configure read buffer limits. The high-water limit is defined by
        # ``self.read_limit``. The ``limit`` argument controls the line length
        # limit and half the buffer limit of :class:`~asyncio.StreamReader`.
        # That's why it must be set to half of ``self.read_limit``.
        self.reader = asyncio.StreamReader(limit=read_limit // 2, loop=loop)

        # Copied from asyncio.FlowControlMixin
        self._paused = False
        self._drain_waiter: Optional[asyncio.Future[None]] = None

        self._drain_lock = asyncio.Lock(**loop_if_py_lt_38(loop))

        # This class implements the data transfer and closing handshake, which
        # are shared between the client-side and the server-side.
        # Subclasses implement the opening handshake and, on success, execute
        # :meth:`connection_open` to change the state to OPEN.
        self.state = State.CONNECTING
        if self.debug:
            self.logger.debug("= connection is CONNECTING")

        # HTTP protocol parameters.
        self.path: str
        self.request_headers: Headers
        self.response_headers: Headers

        # WebSocket protocol parameters.
        self.extensions: List[Extension] = []
        self.subprotocol: Optional[Subprotocol] = None

        # The close code and reason are set when receiving a close frame or
        # losing the TCP connection.
        self.close_code: int
        self.close_reason: str

        # Completed when the connection state becomes CLOSED. Translates the
        # :meth:`connection_lost` callback to a :class:`~asyncio.Future`
        # that can be awaited. (Other :class:`~asyncio.Protocol` callbacks are
        # translated by ``self.stream_reader``).
        self.connection_lost_waiter: asyncio.Future[None] = loop.create_future()

        # Queue of received messages.
        self.messages: Deque[Data] = collections.deque()
        self._pop_message_waiter: Optional[asyncio.Future[None]] = None
        self._put_message_waiter: Optional[asyncio.Future[None]] = None

        # Protect sending fragmented messages.
        self._fragmented_message_waiter: Optional[asyncio.Future[None]] = None

        # Mapping of ping IDs to pong waiters, in chronological order.
        self.pings: Dict[bytes, asyncio.Future[None]] = {}

        # Task running the data transfer.
        self.transfer_data_task: asyncio.Task[None]

        # Exception that occurred during data transfer, if any.
        self.transfer_data_exc: Optional[BaseException] = None

        # Task sending keepalive pings.
        self.keepalive_ping_task: asyncio.Task[None]

        # Task closing the TCP connection.
        self.close_connection_task: asyncio.Task[None]

    # Copied from asyncio.FlowControlMixin
    async def _drain_helper(self) -> None:  # pragma: no cover
        if self.connection_lost_waiter.done():
            raise ConnectionResetError("Connection lost")
        if not self._paused:
            return
        waiter = self._drain_waiter
        assert waiter is None or waiter.cancelled()
        waiter = self.loop.create_future()
        self._drain_waiter = waiter
        await waiter

    # Copied from asyncio.StreamWriter
    async def _drain(self) -> None:  # pragma: no cover
        if self.reader is not None:
            exc = self.reader.exception()
            if exc is not None:
                raise exc
        if self.transport is not None:
            if self.transport.is_closing():
                # Yield to the event loop so connection_lost() may be
                # called.  Without this, _drain_helper() would return
                # immediately, and code that calls
                #     write(...); yield from drain()
                # in a loop would never call connection_lost(), so it
                # would not see an error when the socket is closed.
                await asyncio.sleep(0, **loop_if_py_lt_38(self.loop))
        await self._drain_helper()

    def connection_open(self) -> None:
        """
        Callback when the WebSocket opening handshake completes.

        Enter the OPEN state and start the data transfer phase.

        """
        # 4.1. The WebSocket Connection is Established.
        assert self.state is State.CONNECTING
        self.state = State.OPEN
        if self.debug:
            self.logger.debug("= connection is OPEN")
        # Start the task that receives incoming WebSocket messages.
        self.transfer_data_task = self.loop.create_task(self.transfer_data())
        # Start the task that sends pings at regular intervals.
        self.keepalive_ping_task = self.loop.create_task(self.keepalive_ping())
        # Start the task that eventually closes the TCP connection.
        self.close_connection_task = self.loop.create_task(self.close_connection())

    @property
    def host(self) -> Optional[str]:
        alternative = "remote_address" if self.is_client else "local_address"
        warnings.warn(f"use {alternative}[0] instead of host", DeprecationWarning)
        return self._host

    @property
    def port(self) -> Optional[int]:
        alternative = "remote_address" if self.is_client else "local_address"
        warnings.warn(f"use {alternative}[1] instead of port", DeprecationWarning)
        return self._port

    @property
    def secure(self) -> Optional[bool]:
        warnings.warn("don't use secure", DeprecationWarning)
        return self._secure

    # Public API

    @property
    def local_address(self) -> Any:
        """
        Local address of the connection as a ``(host, port)`` tuple.

        When the connection isn't open, ``local_address`` is ``None``.

        """
        try:
            transport = self.transport
        except AttributeError:
            return None
        else:
            return transport.get_extra_info("sockname")

    @property
    def remote_address(self) -> Any:
        """
        Remote address of the connection as a ``(host, port)`` tuple.

        When the connection isn't open, ``remote_address`` is ``None``.

        """
        try:
            transport = self.transport
        except AttributeError:
            return None
        else:
            return transport.get_extra_info("peername")

    @property
    def open(self) -> bool:
        """
        ``True`` when the connection is usable.

        It may be used to detect disconnections. However, this approach is
        discouraged per the EAFP_ principle.

        When ``open`` is ``False``, using the connection raises a
        :exc:`~websockets.exceptions.ConnectionClosed` exception.

        .. _EAFP: https://docs.python.org/3/glossary.html#term-eafp

        """
        return self.state is State.OPEN and not self.transfer_data_task.done()

    @property
    def closed(self) -> bool:
        """
        ``True`` once the connection is closed.

        Be aware that both :attr:`open` and :attr:`closed` are ``False`` during
        the opening and closing sequences.

        """
        return self.state is State.CLOSED

    async def wait_closed(self) -> None:
        """
        Wait until the connection is closed.

        This is identical to :attr:`closed`, except it can be awaited.

        This can make it easier to handle connection termination, regardless
        of its cause, in tasks that interact with the WebSocket connection.

        """
        await asyncio.shield(self.connection_lost_waiter)

    async def __aiter__(self) -> AsyncIterator[Data]:
        """
        Iterate on received messages.

        Exit normally when the connection is closed with code 1000 or 1001.

        Raise an exception in other cases.

        """
        try:
            while True:
                yield await self.recv()
        except ConnectionClosedOK:
            return

    async def recv(self) -> Data:
        """
        Receive the next message.

        Return a :class:`str` for a text frame and :class:`bytes` for a binary
        frame.

        When the end of the message stream is reached, :meth:`recv` raises
        :exc:`~websockets.exceptions.ConnectionClosed`. Specifically, it
        raises :exc:`~websockets.exceptions.ConnectionClosedOK` after a normal
        connection closure and
        :exc:`~websockets.exceptions.ConnectionClosedError` after a protocol
        error or a network failure.

        Canceling :meth:`recv` is safe. There's no risk of losing the next
        message. The next invocation of :meth:`recv` will return it. This
        makes it possible to enforce a timeout by wrapping :meth:`recv` in
        :func:`~asyncio.wait_for`.

        :raises ~websockets.exceptions.ConnectionClosed: when the
            connection is closed
        :raises RuntimeError: if two coroutines call :meth:`recv` concurrently

        """
        if self._pop_message_waiter is not None:
            raise RuntimeError(
                "cannot call recv while another coroutine "
                "is already waiting for the next message"
            )

        # Don't await self.ensure_open() here:
        # - messages could be available in the queue even if the connection
        #   is closed;
        # - messages could be received before the closing frame even if the
        #   connection is closing.

        # Wait until there's a message in the queue (if necessary) or the
        # connection is closed.
        while len(self.messages) <= 0:
            pop_message_waiter: asyncio.Future[None] = self.loop.create_future()
            self._pop_message_waiter = pop_message_waiter
            try:
                # If asyncio.wait() is canceled, it doesn't cancel
                # pop_message_waiter and self.transfer_data_task.
                await asyncio.wait(
                    [pop_message_waiter, self.transfer_data_task],
                    return_when=asyncio.FIRST_COMPLETED,
                    **loop_if_py_lt_38(self.loop),
                )
            finally:
                self._pop_message_waiter = None

            # If asyncio.wait(...) exited because self.transfer_data_task
            # completed before receiving a new message, raise a suitable
            # exception (or return None if legacy_recv is enabled).
            if not pop_message_waiter.done():
                if self.legacy_recv:
                    return None  # type: ignore
                else:
                    # Wait until the connection is closed to raise
                    # ConnectionClosed with the correct code and reason.
                    await self.ensure_open()

        # Pop a message from the queue.
        message = self.messages.popleft()

        # Notify transfer_data().
        if self._put_message_waiter is not None:
            self._put_message_waiter.set_result(None)
            self._put_message_waiter = None

        return message

    async def send(
        self, message: Union[Data, Iterable[Data], AsyncIterable[Data]]
    ) -> None:
        """
        Send a message.

        A string (:class:`str`) is sent as a `Text frame`_. A bytestring or
        bytes-like object (:class:`bytes`, :class:`bytearray`, or
        :class:`memoryview`) is sent as a `Binary frame`_.

        .. _Text frame: https://tools.ietf.org/html/rfc6455#section-5.6
        .. _Binary frame: https://tools.ietf.org/html/rfc6455#section-5.6

        :meth:`send` also accepts an iterable or an asynchronous iterable of
        strings, bytestrings, or bytes-like objects. In that case the message
        is fragmented. Each item is treated as a message fragment and sent in
        its own frame. All items must be of the same type, or else
        :meth:`send` will raise a :exc:`TypeError` and the connection will be
        closed.

        :meth:`send` rejects dict-like objects because this is often an error.
        If you wish to send the keys of a dict-like object as fragments, call
        its :meth:`~dict.keys` method and pass the result to :meth:`send`.

        Canceling :meth:`send` is discouraged. Instead, you should close the
        connection with :meth:`close`. Indeed, there are only two situations
        where :meth:`send` may yield control to the event loop:

        1. The write buffer is full. If you don't want to wait until enough
           data is sent, your only alternative is to close the connection.
           :meth:`close` will likely time out then abort the TCP connection.
        2. ``message`` is an asynchronous iterator that yields control.
           Stopping in the middle of a fragmented message will cause a
           protocol error. Closing the connection has the same effect.

        :raises ~websockets.exceptions.ConnectionClosed: when the
            connection is closed
        :raises TypeError: for unsupported inputs

        """
        await self.ensure_open()

        # While sending a fragmented message, prevent sending other messages
        # until all fragments are sent.
        while self._fragmented_message_waiter is not None:
            await asyncio.shield(self._fragmented_message_waiter)

        # Unfragmented message -- this case must be handled first because
        # strings and bytes-like objects are iterable.

        if isinstance(message, (str, bytes, bytearray, memoryview)):
            opcode, data = prepare_data(message)
            await self.write_frame(True, opcode, data)

        # Catch a common mistake -- passing a dict to send().

        elif isinstance(message, Mapping):
            raise TypeError("data is a dict-like object")

        # Fragmented message -- regular iterator.

        elif isinstance(message, Iterable):

            # Work around https://github.com/python/mypy/issues/6227
            message = cast(Iterable[Data], message)

            iter_message = iter(message)
            try:
                message_chunk = next(iter_message)
            except StopIteration:
                return
            opcode, data = prepare_data(message_chunk)

            self._fragmented_message_waiter = asyncio.Future()
            try:
                # First fragment.
                await self.write_frame(False, opcode, data)

                # Other fragments.
                for message_chunk in iter_message:
                    confirm_opcode, data = prepare_data(message_chunk)
                    if confirm_opcode != opcode:
                        raise TypeError("data contains inconsistent types")
                    await self.write_frame(False, OP_CONT, data)

                # Final fragment.
                await self.write_frame(True, OP_CONT, b"")

            except Exception:
                # We're half-way through a fragmented message and we can't
                # complete it. This makes the connection unusable.
                self.fail_connection(1011)
                raise

            finally:
                self._fragmented_message_waiter.set_result(None)
                self._fragmented_message_waiter = None

        # Fragmented message -- asynchronous iterator

        elif isinstance(message, AsyncIterable):
            # aiter_message = aiter(message) without aiter
            # https://github.com/python/mypy/issues/5738
            aiter_message = type(message).__aiter__(message)  # type: ignore
            try:
                # message_chunk = anext(aiter_message) without anext
                # https://github.com/python/mypy/issues/5738
                message_chunk = await type(aiter_message).__anext__(  # type: ignore
                    aiter_message
                )
            except StopAsyncIteration:
                return
            opcode, data = prepare_data(message_chunk)

            self._fragmented_message_waiter = asyncio.Future()
            try:
                # First fragment.
                await self.write_frame(False, opcode, data)

                # Other fragments.
                # https://github.com/python/mypy/issues/5738
                # coverage reports this code as not covered, but it is
                # exercised by tests - changing it breaks the tests!
                async for message_chunk in aiter_message:  # type: ignore  # pragma: no cover  # noqa
                    confirm_opcode, data = prepare_data(message_chunk)
                    if confirm_opcode != opcode:
                        raise TypeError("data contains inconsistent types")
                    await self.write_frame(False, OP_CONT, data)

                # Final fragment.
                await self.write_frame(True, OP_CONT, b"")

            except Exception:
                # We're half-way through a fragmented message and we can't
                # complete it. This makes the connection unusable.
                self.fail_connection(1011)
                raise

            finally:
                self._fragmented_message_waiter.set_result(None)
                self._fragmented_message_waiter = None

        else:
            raise TypeError("data must be bytes, str, or iterable")

    async def close(self, code: int = 1000, reason: str = "") -> None:
        """
        Perform the closing handshake.

        :meth:`close` waits for the other end to complete the handshake and
        for the TCP connection to terminate. As a consequence, there's no need
        to await :meth:`wait_closed`; :meth:`close` already does it.

        :meth:`close` is idempotent: it doesn't do anything once the
        connection is closed.

        Wrapping :func:`close` in :func:`~asyncio.create_task` is safe, given
        that errors during connection termination aren't particularly useful.

        Canceling :meth:`close` is discouraged. If it takes too long, you can
        set a shorter ``close_timeout``. If you don't want to wait, let the
        Python process exit, then the OS will close the TCP connection.

        :param code: WebSocket close code
        :param reason: WebSocket close reason

        """
        try:
            await asyncio.wait_for(
                self.write_close_frame(serialize_close(code, reason)),
                self.close_timeout,
                **loop_if_py_lt_38(self.loop),
            )
        except asyncio.TimeoutError:
            # If the close frame cannot be sent because the send buffers
            # are full, the closing handshake won't complete anyway.
            # Fail the connection to shut down faster.
            self.fail_connection()

        # If no close frame is received within the timeout, wait_for() cancels
        # the data transfer task and raises TimeoutError.

        # If close() is called multiple times concurrently and one of these
        # calls hits the timeout, the data transfer task will be cancelled.
        # Other calls will receive a CancelledError here.

        try:
            # If close() is canceled during the wait, self.transfer_data_task
            # is canceled before the timeout elapses.
            await asyncio.wait_for(
                self.transfer_data_task,
                self.close_timeout,
                **loop_if_py_lt_38(self.loop),
            )
        except (asyncio.TimeoutError, asyncio.CancelledError):
            pass

        # Wait for the close connection task to close the TCP connection.
        await asyncio.shield(self.close_connection_task)

    async def ping(self, data: Optional[Data] = None) -> Awaitable[None]:
        """
        Send a ping.

        Return a :class:`~asyncio.Future` that will be completed when the
        corresponding pong is received. You can ignore it if you don't intend
        to wait.

        A ping may serve as a keepalive or as a check that the remote endpoint
        received all messages up to this point::

            pong_waiter = await ws.ping()
            await pong_waiter  # only if you want to wait for the pong

        By default, the ping contains four random bytes. This payload may be
        overridden with the optional ``data`` argument which must be a string
        (which will be encoded to UTF-8) or a bytes-like object.

        Canceling :meth:`ping` is discouraged. If :meth:`ping` doesn't return
        immediately, it means the write buffer is full. If you don't want to
        wait, you should close the connection.

        Canceling the :class:`~asyncio.Future` returned by :meth:`ping` has no
        effect.

        :raises ~websockets.exceptions.ConnectionClosed: when the
            connection is closed
        :raises ValueError: if another ping was sent with the same data and
            the corresponding pong wasn't received yet

        """
        await self.ensure_open()

        if data is not None:
            data = prepare_ctrl(data)

        # Protect against duplicates if a payload is explicitly set.
        if data in self.pings:
            raise ValueError("already waiting for a pong with the same data")

        # Generate a unique random payload otherwise.
        while data is None or data in self.pings:
            data = struct.pack("!I", random.getrandbits(32))

        self.pings[data] = self.loop.create_future()

        await self.write_frame(True, OP_PING, data)

        return asyncio.shield(self.pings[data])

    async def pong(self, data: Data = b"") -> None:
        """
        Send a pong.

        An unsolicited pong may serve as a unidirectional heartbeat.

        The payload may be set with the optional ``data`` argument which must
        be a string (which will be encoded to UTF-8) or a bytes-like object.

        Canceling :meth:`pong` is discouraged for the same reason as
        :meth:`ping`.

        :raises ~websockets.exceptions.ConnectionClosed: when the
            connection is closed

        """
        await self.ensure_open()

        data = prepare_ctrl(data)

        await self.write_frame(True, OP_PONG, data)

    # Private methods - no guarantees.

    def connection_closed_exc(self) -> ConnectionClosed:
        exception: ConnectionClosed
        if self.close_code == 1000 or self.close_code == 1001:
            exception = ConnectionClosedOK(self.close_code, self.close_reason)
        else:
            exception = ConnectionClosedError(self.close_code, self.close_reason)
        # Chain to the exception that terminated data transfer, if any.
        exception.__cause__ = self.transfer_data_exc
        return exception

    async def ensure_open(self) -> None:
        """
        Check that the WebSocket connection is open.

        Raise :exc:`~websockets.exceptions.ConnectionClosed` if it isn't.

        """
        # Handle cases from most common to least common for performance.
        if self.state is State.OPEN:
            # If self.transfer_data_task exited without a closing handshake,
            # self.close_connection_task may be closing the connection, going
            # straight from OPEN to CLOSED.
            if self.transfer_data_task.done():
                await asyncio.shield(self.close_connection_task)
                raise self.connection_closed_exc()
            else:
                return

        if self.state is State.CLOSED:
            raise self.connection_closed_exc()

        if self.state is State.CLOSING:
            # If we started the closing handshake, wait for its completion to
            # get the proper close code and reason. self.close_connection_task
            # will complete within 4 or 5 * close_timeout after close(). The
            # CLOSING state also occurs when failing the connection. In that
            # case self.close_connection_task will complete even faster.
            await asyncio.shield(self.close_connection_task)
            raise self.connection_closed_exc()

        # Control may only reach this point in buggy third-party subclasses.
        assert self.state is State.CONNECTING
        raise InvalidState("WebSocket connection isn't established yet")

    async def transfer_data(self) -> None:
        """
        Read incoming messages and put them in a queue.

        This coroutine runs in a task until the closing handshake is started.

        """
        try:
            while True:
                message = await self.read_message()

                # Exit the loop when receiving a close frame.
                if message is None:
                    break

                # Wait until there's room in the queue (if necessary).
                if self.max_queue is not None:
                    while len(self.messages) >= self.max_queue:
                        self._put_message_waiter = self.loop.create_future()
                        try:
                            await asyncio.shield(self._put_message_waiter)
                        finally:
                            self._put_message_waiter = None

                # Put the message in the queue.
                self.messages.append(message)

                # Notify recv().
                if self._pop_message_waiter is not None:
                    self._pop_message_waiter.set_result(None)
                    self._pop_message_waiter = None

        except asyncio.CancelledError as exc:
            self.transfer_data_exc = exc
            # If fail_connection() cancels this task, avoid logging the error
            # twice and failing the connection again.
            raise

        except ProtocolError as exc:
            self.transfer_data_exc = exc
            self.fail_connection(1002)

        except (ConnectionError, TimeoutError, EOFError) as exc:
            # Reading data with self.reader.readexactly may raise:
            # - most subclasses of ConnectionError if the TCP connection
            #   breaks, is reset, or is aborted;
            # - TimeoutError if the TCP connection times out;
            # - IncompleteReadError, a subclass of EOFError, if fewer
            #   bytes are available than requested.
            self.transfer_data_exc = exc
            self.fail_connection(1006)

        except UnicodeDecodeError as exc:
            self.transfer_data_exc = exc
            self.fail_connection(1007)

        except PayloadTooBig as exc:
            self.transfer_data_exc = exc
            self.fail_connection(1009)

        except Exception as exc:
            # This shouldn't happen often because exceptions expected under
            # regular circumstances are handled above. If it does, consider
            # catching and handling more exceptions.
            self.logger.error("data transfer failed", exc_info=True)

            self.transfer_data_exc = exc
            self.fail_connection(1011)

    async def read_message(self) -> Optional[Data]:
        """
        Read a single message from the connection.

        Re-assemble data frames if the message is fragmented.

        Return ``None`` when the closing handshake is started.

        """
        frame = await self.read_data_frame(max_size=self.max_size)

        # A close frame was received.
        if frame is None:
            return None

        if frame.opcode == OP_TEXT:
            text = True
        elif frame.opcode == OP_BINARY:
            text = False
        else:  # frame.opcode == OP_CONT
            raise ProtocolError("unexpected opcode")

        # Shortcut for the common case - no fragmentation
        if frame.fin:
            return frame.data.decode("utf-8") if text else frame.data

        # 5.4. Fragmentation
        chunks: List[Data] = []
        max_size = self.max_size
        if text:
            decoder_factory = codecs.getincrementaldecoder("utf-8")
            decoder = decoder_factory(errors="strict")
            if max_size is None:

                def append(frame: Frame) -> None:
                    nonlocal chunks
                    chunks.append(decoder.decode(frame.data, frame.fin))

            else:

                def append(frame: Frame) -> None:
                    nonlocal chunks, max_size
                    chunks.append(decoder.decode(frame.data, frame.fin))
                    assert isinstance(max_size, int)
                    max_size -= len(frame.data)

        else:
            if max_size is None:

                def append(frame: Frame) -> None:
                    nonlocal chunks
                    chunks.append(frame.data)

            else:

                def append(frame: Frame) -> None:
                    nonlocal chunks, max_size
                    chunks.append(frame.data)
                    assert isinstance(max_size, int)
                    max_size -= len(frame.data)

        append(frame)

        while not frame.fin:
            frame = await self.read_data_frame(max_size=max_size)
            if frame is None:
                raise ProtocolError("incomplete fragmented message")
            if frame.opcode != OP_CONT:
                raise ProtocolError("unexpected opcode")
            append(frame)

        # mypy cannot figure out that chunks have the proper type.
        return ("" if text else b"").join(chunks)  # type: ignore

    async def read_data_frame(self, max_size: Optional[int]) -> Optional[Frame]:
        """
        Read a single data frame from the connection.

        Process control frames received before the next data frame.

        Return ``None`` if a close frame is encountered before any data frame.

        """
        # 6.2. Receiving Data
        while True:
            frame = await self.read_frame(max_size)

            # 5.5. Control Frames
            if frame.opcode == OP_CLOSE:
                # 7.1.5.  The WebSocket Connection Close Code
                # 7.1.6.  The WebSocket Connection Close Reason
                self.close_code, self.close_reason = parse_close(frame.data)
                try:
                    # Echo the original data instead of re-serializing it with
                    # serialize_close() because that fails when the close frame
                    # is empty and parse_close() synthetizes a 1005 close code.
                    await self.write_close_frame(frame.data)
                except ConnectionClosed:
                    # It doesn't really matter if the connection was closed
                    # before we could send back a close frame.
                    pass
                return None

            elif frame.opcode == OP_PING:
                # Answer pings.
                await self.pong(frame.data)

            elif frame.opcode == OP_PONG:
                if frame.data in self.pings:
                    # Sending a pong for only the most recent ping is legal.
                    # Acknowledge all previous pings too in that case.
                    ping_id = None
                    ping_ids = []
                    for ping_id, ping in self.pings.items():
                        ping_ids.append(ping_id)
                        if not ping.done():
                            ping.set_result(None)
                        if ping_id == frame.data:
                            break
                    else:  # pragma: no cover
                        assert False, "ping_id is in self.pings"
                    # Remove acknowledged pings from self.pings.
                    for ping_id in ping_ids:
                        del self.pings[ping_id]

            # 5.6. Data Frames
            else:
                return frame

    async def read_frame(self, max_size: Optional[int]) -> Frame:
        """
        Read a single frame from the connection.

        """
        frame = await Frame.read(
            self.reader.readexactly,
            mask=not self.is_client,
            max_size=max_size,
            extensions=self.extensions,
        )
        if self.debug:
            self.logger.debug("< %s", frame)
        return frame

    async def write_frame(
        self, fin: bool, opcode: int, data: bytes, *, _expected_state: int = State.OPEN
    ) -> None:
        # Defensive assertion for protocol compliance.
        if self.state is not _expected_state:  # pragma: no cover
            raise InvalidState(
                f"Cannot write to a WebSocket in the {self.state.name} state"
            )

        frame = Frame(fin, Opcode(opcode), data)
        if self.debug:
            self.logger.debug("> %s", frame)
        frame.write(
            self.transport.write,
            mask=self.is_client,
            extensions=self.extensions,
        )

        try:
            # drain() cannot be called concurrently by multiple coroutines:
            # http://bugs.python.org/issue29930. Remove this lock when no
            # version of Python where this bugs exists is supported anymore.
            async with self._drain_lock:
                # Handle flow control automatically.
                await self._drain()
        except ConnectionError:
            # Terminate the connection if the socket died.
            self.fail_connection()
            # Wait until the connection is closed to raise ConnectionClosed
            # with the correct code and reason.
            await self.ensure_open()

    async def write_close_frame(self, data: bytes = b"") -> None:
        """
        Write a close frame if and only if the connection state is OPEN.

        This dedicated coroutine must be used for writing close frames to
        ensure that at most one close frame is sent on a given connection.

        """
        # Test and set the connection state before sending the close frame to
        # avoid sending two frames in case of concurrent calls.
        if self.state is State.OPEN:
            # 7.1.3. The WebSocket Closing Handshake is Started
            self.state = State.CLOSING
            if self.debug:
                self.logger.debug("= connection is CLOSING")

            # 7.1.2. Start the WebSocket Closing Handshake
            await self.write_frame(True, OP_CLOSE, data, _expected_state=State.CLOSING)

    async def keepalive_ping(self) -> None:
        """
        Send a Ping frame and wait for a Pong frame at regular intervals.

        This coroutine exits when the connection terminates and one of the
        following happens:

        - :meth:`ping` raises :exc:`ConnectionClosed`, or
        - :meth:`close_connection` cancels :attr:`keepalive_ping_task`.

        """
        if self.ping_interval is None:
            return

        try:
            while True:
                await asyncio.sleep(
                    self.ping_interval,
                    **loop_if_py_lt_38(self.loop),
                )

                # ping() raises CancelledError if the connection is closed,
                # when close_connection() cancels self.keepalive_ping_task.

                # ping() raises ConnectionClosed if the connection is lost,
                # when connection_lost() calls abort_pings().

                self.logger.debug("%% sending keepalive ping")
                pong_waiter = await self.ping()

                if self.ping_timeout is not None:
                    try:
                        await asyncio.wait_for(
                            pong_waiter,
                            self.ping_timeout,
                            **loop_if_py_lt_38(self.loop),
                        )
                        self.logger.debug("%% received keepalive pong")
                    except asyncio.TimeoutError:
                        if self.debug:
                            self.logger.debug("! timed out waiting for keepalive pong")
                        self.fail_connection(1011)
                        break

        # Remove this branch when dropping support for Python < 3.8
        # because CancelledError no longer inherits Exception.
        except asyncio.CancelledError:
            raise

        except ConnectionClosed:
            pass

        except Exception:
            self.logger.error("keepalive ping failed", exc_info=True)

    async def close_connection(self) -> None:
        """
        7.1.1. Close the WebSocket Connection

        When the opening handshake succeeds, :meth:`connection_open` starts
        this coroutine in a task. It waits for the data transfer phase to
        complete then it closes the TCP connection cleanly.

        When the opening handshake fails, :meth:`fail_connection` does the
        same. There's no data transfer phase in that case.

        """
        try:
            # Wait for the data transfer phase to complete.
            if hasattr(self, "transfer_data_task"):
                try:
                    await self.transfer_data_task
                except asyncio.CancelledError:
                    pass

            # Cancel the keepalive ping task.
            if hasattr(self, "keepalive_ping_task"):
                self.keepalive_ping_task.cancel()

            # A client should wait for a TCP close from the server.
            if self.is_client and hasattr(self, "transfer_data_task"):
                if await self.wait_for_connection_lost():
                    # Coverage marks this line as a partially executed branch.
                    # I supect a bug in coverage. Ignore it for now.
                    return  # pragma: no cover
                if self.debug:
                    self.logger.debug("! timed out waiting for TCP close")

            # Half-close the TCP connection if possible (when there's no TLS).
            if self.transport.can_write_eof():
                if self.debug:
                    self.logger.debug("x half-closing TCP connection")
                self.transport.write_eof()

                if await self.wait_for_connection_lost():
                    # Coverage marks this line as a partially executed branch.
                    # I supect a bug in coverage. Ignore it for now.
                    return  # pragma: no cover
                if self.debug:
                    self.logger.debug("! timed out waiting for TCP close")

        finally:
            # The try/finally ensures that the transport never remains open,
            # even if this coroutine is canceled (for example).
            await self.close_transport()

    async def close_transport(self) -> None:
        """
        Close the TCP connection.

        """
        # If connection_lost() was called, the TCP connection is closed.
        # However, if TLS is enabled, the transport still needs closing.
        # Else asyncio complains: ResourceWarning: unclosed transport.
        if self.connection_lost_waiter.done() and self.transport.is_closing():
            return

        # Close the TCP connection. Buffers are flushed asynchronously.
        if self.debug:
            self.logger.debug("x closing TCP connection")
        self.transport.close()

        if await self.wait_for_connection_lost():
            return
        if self.debug:
            self.logger.debug("! timed out waiting for TCP close")

        # Abort the TCP connection. Buffers are discarded.
        if self.debug:
            self.logger.debug("x aborting TCP connection")
        self.transport.abort()

        # connection_lost() is called quickly after aborting.
        # Coverage marks this line as a partially executed branch.
        # I supect a bug in coverage. Ignore it for now.
        await self.wait_for_connection_lost()  # pragma: no cover

    async def wait_for_connection_lost(self) -> bool:
        """
        Wait until the TCP connection is closed or ``self.close_timeout`` elapses.

        Return ``True`` if the connection is closed and ``False`` otherwise.

        """
        if not self.connection_lost_waiter.done():
            try:
                await asyncio.wait_for(
                    asyncio.shield(self.connection_lost_waiter),
                    self.close_timeout,
                    **loop_if_py_lt_38(self.loop),
                )
            except asyncio.TimeoutError:
                pass
        # Re-check self.connection_lost_waiter.done() synchronously because
        # connection_lost() could run between the moment the timeout occurs
        # and the moment this coroutine resumes running.
        return self.connection_lost_waiter.done()

    def fail_connection(self, code: int = 1006, reason: str = "") -> None:
        """
        7.1.7. Fail the WebSocket Connection

        This requires:

        1. Stopping all processing of incoming data, which means cancelling
           :attr:`transfer_data_task`. The close code will be 1006 unless a
           close frame was received earlier.

        2. Sending a close frame with an appropriate code if the opening
           handshake succeeded and the other side is likely to process it.

        3. Closing the connection. :meth:`close_connection` takes care of
           this once :attr:`transfer_data_task` exits after being canceled.

        (The specification describes these steps in the opposite order.)

        """
        if self.debug:
            self.logger.debug("! failing connection with code %d", code)

        # Cancel transfer_data_task if the opening handshake succeeded.
        # cancel() is idempotent and ignored if the task is done already.
        if hasattr(self, "transfer_data_task"):
            self.transfer_data_task.cancel()

        # Send a close frame when the state is OPEN (a close frame was already
        # sent if it's CLOSING), except when failing the connection because of
        # an error reading from or writing to the network.
        # Don't send a close frame if the connection is broken.
        if code != 1006 and self.state is State.OPEN:

            frame_data = serialize_close(code, reason)

            # Write the close frame without draining the write buffer.

            # Keeping fail_connection() synchronous guarantees it can't
            # get stuck and simplifies the implementation of the callers.
            # Not drainig the write buffer is acceptable in this context.

            # This duplicates a few lines of code from write_close_frame()
            # and write_frame().

            self.state = State.CLOSING
            if self.debug:
                self.logger.debug("= connection is CLOSING")

            frame = Frame(True, OP_CLOSE, frame_data)
            if self.debug:
                self.logger.debug("> %s", frame)
            frame.write(
                self.transport.write,
                mask=self.is_client,
                extensions=self.extensions,
            )

        # Start close_connection_task if the opening handshake didn't succeed.
        if not hasattr(self, "close_connection_task"):
            self.close_connection_task = self.loop.create_task(self.close_connection())

    def abort_pings(self) -> None:
        """
        Raise ConnectionClosed in pending keepalive pings.

        They'll never receive a pong once the connection is closed.

        """
        assert self.state is State.CLOSED
        exc = self.connection_closed_exc()

        for ping in self.pings.values():
            ping.set_exception(exc)
            # If the exception is never retrieved, it will be logged when ping
            # is garbage-collected. This is confusing for users.
            # Given that ping is done (with an exception), canceling it does
            # nothing, but it prevents logging the exception.
            ping.cancel()

        if self.debug:
            if self.pings:
                pings_hex = ", ".join(
                    ping_id.hex() or "[empty]" for ping_id in self.pings
                )
                plural = "s" if len(self.pings) > 1 else ""
                self.logger.debug("% aborted pending ping%s: %s", plural, pings_hex)

    # asyncio.Protocol methods

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        """
        Configure write buffer limits.

        The high-water limit is defined by ``self.write_limit``.

        The low-water limit currently defaults to ``self.write_limit // 4`` in
        :meth:`~asyncio.WriteTransport.set_write_buffer_limits`, which should
        be all right for reasonable use cases of this library.

        This is the earliest point where we can get hold of the transport,
        which means it's the best point for configuring it.

        """
        transport = cast(asyncio.Transport, transport)
        transport.set_write_buffer_limits(self.write_limit)
        self.transport = transport

        # Copied from asyncio.StreamReaderProtocol
        self.reader.set_transport(transport)

    def connection_lost(self, exc: Optional[Exception]) -> None:
        """
        7.1.4. The WebSocket Connection is Closed.

        """
        self.state = State.CLOSED
        if not hasattr(self, "close_code"):
            self.close_code = 1006
        if not hasattr(self, "close_reason"):
            self.close_reason = ""
        self.logger.debug(
            "= connection is CLOSED - code = %d, reason = %s",
            self.close_code,
            self.close_reason or "[no reason]",
        )

        self.abort_pings()

        # If self.connection_lost_waiter isn't pending, that's a bug, because:
        # - it's set only here in connection_lost() which is called only once;
        # - it must never be canceled.
        self.connection_lost_waiter.set_result(None)

        if True:  # pragma: no cover

            # Copied from asyncio.StreamReaderProtocol
            if self.reader is not None:
                if exc is None:
                    self.reader.feed_eof()
                else:
                    self.reader.set_exception(exc)

            # Copied from asyncio.FlowControlMixin
            # Wake up the writer if currently paused.
            if not self._paused:
                return
            waiter = self._drain_waiter
            if waiter is None:
                return
            self._drain_waiter = None
            if waiter.done():
                return
            if exc is None:
                waiter.set_result(None)
            else:
                waiter.set_exception(exc)

    def pause_writing(self) -> None:  # pragma: no cover
        assert not self._paused
        self._paused = True

    def resume_writing(self) -> None:  # pragma: no cover
        assert self._paused
        self._paused = False

        waiter = self._drain_waiter
        if waiter is not None:
            self._drain_waiter = None
            if not waiter.done():
                waiter.set_result(None)

    def data_received(self, data: bytes) -> None:
        self.reader.feed_data(data)

    def eof_received(self) -> None:
        """
        Close the transport after receiving EOF.

        The WebSocket protocol has its own closing handshake: endpoints close
        the TCP or TLS connection after sending and receiving a close frame.

        As a consequence, they never need to write after receiving EOF, so
        there's no reason to keep the transport open by returning ``True``.

        Besides, that doesn't work on TLS connections.

        """
        self.reader.feed_eof()
