from __future__ import annotations

import asyncio
import codecs
import collections
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

from ..connection import State
from ..datastructures import Headers
from ..exceptions import (
    ConnectionClosed,
    ConnectionClosedError,
    ConnectionClosedOK,
    InvalidState,
    PayloadTooBig,
    ProtocolError,
)
from ..extensions import Extension
from ..frames import (
    OK_CLOSE_CODES,
    OP_BINARY,
    OP_CLOSE,
    OP_CONT,
    OP_PING,
    OP_PONG,
    OP_TEXT,
    Close,
    Opcode,
    prepare_ctrl,
    prepare_data,
)
from ..typing import Data, LoggerLike, Subprotocol
from .compatibility import loop_if_py_lt_38
from .framing import Frame


__all__ = ["WebSocketCommonProtocol", "broadcast"]


# In order to ensure consistency, the code always checks the current value of
# WebSocketCommonProtocol.state before assigning a new value and never yields
# between the check and the assignment.


class WebSocketCommonProtocol(asyncio.Protocol):
    """
    WebSocket connection.

    :class:`WebSocketCommonProtocol` provides APIs shared between WebSocket
    servers and clients. You shouldn't use it directly. Instead, use
    :class:`~websockets.client.WebSocketClientProtocol` or
    :class:`~websockets.server.WebSocketServerProtocol`.

    This documentation focuses on low-level details that aren't covered in the
    documentation of :class:`~websockets.client.WebSocketClientProtocol` and
    :class:`~websockets.server.WebSocketServerProtocol` for the sake of
    simplicity.

    Once the connection is open, a Ping_ frame is sent every ``ping_interval``
    seconds. This serves as a keepalive. It helps keeping the connection
    open, especially in the presence of proxies with short timeouts on
    inactive connections. Set ``ping_interval`` to :obj:`None` to disable
    this behavior.

    .. _Ping: https://www.rfc-editor.org/rfc/rfc6455.html#section-5.5.2

    If the corresponding Pong_ frame isn't received within ``ping_timeout``
    seconds, the connection is considered unusable and is closed with code
    1011. This ensures that the remote endpoint remains responsive. Set
    ``ping_timeout`` to :obj:`None` to disable this behavior.

    .. _Pong: https://www.rfc-editor.org/rfc/rfc6455.html#section-5.5.3

    The ``close_timeout`` parameter defines a maximum wait time for completing
    the closing handshake and terminating the TCP connection. For legacy
    reasons, :meth:`close` completes in at most ``5 * close_timeout`` seconds
    for clients and ``4 * close_timeout`` for servers.

    See the discussion of :doc:`timeouts <../topics/timeouts>` for details.

    ``close_timeout`` needs to be a parameter of the protocol because
    websockets usually calls :meth:`close` implicitly upon exit:

    * on the client side, when :func:`~websockets.client.connect` is used as a
      context manager;
    * on the server side, when the connection handler terminates;

    To apply a timeout to any other API, wrap it in :func:`~asyncio.wait_for`.

    The ``max_size`` parameter enforces the maximum size for incoming messages
    in bytes. The default value is 1 MiB. If a larger message is received,
    :meth:`recv` will raise :exc:`~websockets.exceptions.ConnectionClosedError`
    and the connection will be closed with code 1009.

    The ``max_queue`` parameter sets the maximum length of the queue that
    holds incoming messages. The default value is ``32``. Messages are added
    to an in-memory queue when they're received; then :meth:`recv` pops from
    that queue. In order to prevent excessive memory consumption when
    messages are received faster than they can be processed, the queue must
    be bounded. If the queue fills up, the protocol stops processing incoming
    data until :meth:`recv` is called. In this situation, various receive
    buffers (at least in :mod:`asyncio` and in the OS) will fill up, then the
    TCP receive window will shrink, slowing down transmission to avoid packet
    loss.

    Since Python can use up to 4 bytes of memory to represent a single
    character, each connection may use up to ``4 * max_size * max_queue``
    bytes of memory to store incoming messages. By default, this is 128 MiB.
    You may want to lower the limits, depending on your application's
    requirements.

    The ``read_limit`` argument sets the high-water limit of the buffer for
    incoming bytes. The low-water limit is half the high-water limit. The
    default value is 64 KiB, half of asyncio's default (based on the current
    implementation of :class:`~asyncio.StreamReader`).

    The ``write_limit`` argument sets the high-water limit of the buffer for
    outgoing bytes. The low-water limit is a quarter of the high-water limit.
    The default value is 64 KiB, equal to asyncio's default (based on the
    current implementation of ``FlowControlMixin``).

    See the discussion of :doc:`memory usage <../topics/memory>` for details.

    Args:
        logger: logger for this connection;
            defaults to ``logging.getLogger("websockets.protocol")``;
            see the :doc:`logging guide <../topics/logging>` for details.
        ping_interval: delay between keepalive pings in seconds;
            :obj:`None` to disable keepalive pings.
        ping_timeout: timeout for keepalive pings in seconds;
            :obj:`None` to disable timeouts.
        close_timeout: timeout for closing the connection in seconds;
            for legacy reasons, the actual timeout is 4 or 5 times larger.
        max_size: maximum size of incoming messages in bytes;
            :obj:`None` to disable the limit.
        max_queue: maximum number of incoming messages in receive buffer;
            :obj:`None` to disable the limit.
        read_limit: high-water mark of read buffer in bytes.
        write_limit: high-water mark of write buffer in bytes.

    """

    # There are only two differences between the client-side and server-side
    # behavior: masking the payload and closing the underlying TCP connection.
    # Set is_client = True/False and side = "client"/"server" to pick a side.
    is_client: bool
    side: str = "undefined"

    def __init__(
        self,
        *,
        logger: Optional[LoggerLike] = None,
        ping_interval: Optional[float] = 20,
        ping_timeout: Optional[float] = 20,
        close_timeout: Optional[float] = None,
        max_size: Optional[int] = 2 ** 20,
        max_queue: Optional[int] = 2 ** 5,
        read_limit: int = 2 ** 16,
        write_limit: int = 2 ** 16,
        # The following arguments are kept only for backwards compatibility.
        host: Optional[str] = None,
        port: Optional[int] = None,
        secure: Optional[bool] = None,
        legacy_recv: bool = False,
        loop: Optional[asyncio.AbstractEventLoop] = None,
        timeout: Optional[float] = None,
    ) -> None:
        if legacy_recv:  # pragma: no cover
            warnings.warn("legacy_recv is deprecated", DeprecationWarning)

        # Backwards compatibility: close_timeout used to be called timeout.
        if timeout is None:
            timeout = 10
        else:
            warnings.warn("rename timeout to close_timeout", DeprecationWarning)
        # If both are specified, timeout is ignored.
        if close_timeout is None:
            close_timeout = timeout

        # Backwards compatibility: the loop parameter used to be supported.
        if loop is None:
            loop = asyncio.get_event_loop()
        else:
            warnings.warn("remove loop argument", DeprecationWarning)

        self.ping_interval = ping_interval
        self.ping_timeout = ping_timeout
        self.close_timeout = close_timeout
        self.max_size = max_size
        self.max_queue = max_queue
        self.read_limit = read_limit
        self.write_limit = write_limit

        # Unique identifier. For logs.
        self.id: uuid.UUID = uuid.uuid4()
        """Unique identifier of the connection. Useful in logs."""

        # Logger or LoggerAdapter for this connection.
        if logger is None:
            logger = logging.getLogger("websockets.protocol")
        # https://github.com/python/typeshed/issues/5561
        logger = cast(logging.Logger, logger)
        self.logger: LoggerLike = logging.LoggerAdapter(logger, {"websocket": self})
        """Logger for this connection."""

        # Track if DEBUG is enabled. Shortcut logging calls if it isn't.
        self.debug = logger.isEnabledFor(logging.DEBUG)

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
        """Path of the opening handshake request."""
        self.request_headers: Headers
        """Opening handshake request headers."""
        self.response_headers: Headers
        """Opening handshake response headers."""

        # WebSocket protocol parameters.
        self.extensions: List[Extension] = []
        self.subprotocol: Optional[Subprotocol] = None
        """Subprotocol, if one was negotiated."""

        # Close code and reason, set when a close frame is sent or received.
        self.close_rcvd: Optional[Close] = None
        self.close_sent: Optional[Close] = None
        self.close_rcvd_then_sent: Optional[bool] = None

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
        Local address of the connection.

        For IPv4 connections, this is a ``(host, port)`` tuple.

        The format of the address depends on the address family;
        see :meth:`~socket.socket.getsockname`.

        :obj:`None` if the TCP connection isn't established yet.

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
        Remote address of the connection.

        For IPv4 connections, this is a ``(host, port)`` tuple.

        The format of the address depends on the address family;
        see :meth:`~socket.socket.getpeername`.

        :obj:`None` if the TCP connection isn't established yet.

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
        :obj:`True` when the connection is open; :obj:`False` otherwise.

        This attribute may be used to detect disconnections. However, this
        approach is discouraged per the EAFP_ principle. Instead, you should
        handle :exc:`~websockets.exceptions.ConnectionClosed` exceptions.

        .. _EAFP: https://docs.python.org/3/glossary.html#term-eafp

        """
        return self.state is State.OPEN and not self.transfer_data_task.done()

    @property
    def closed(self) -> bool:
        """
        :obj:`True` when the connection is closed; :obj:`False` otherwise.

        Be aware that both :attr:`open` and :attr:`closed` are :obj:`False`
        during the opening and closing sequences.

        """
        return self.state is State.CLOSED

    @property
    def close_code(self) -> Optional[int]:
        """
        WebSocket close code, defined in `section 7.1.5 of RFC 6455`_.

        .. _section 7.1.5 of RFC 6455:
            https://www.rfc-editor.org/rfc/rfc6455.html#section-7.1.5

        :obj:`None` if the connection isn't closed yet.

        """
        if self.state is not State.CLOSED:
            return None
        elif self.close_rcvd is None:
            return 1006
        else:
            return self.close_rcvd.code

    @property
    def close_reason(self) -> Optional[str]:
        """
        WebSocket close reason, defined in `section 7.1.6 of RFC 6455`_.

        .. _section 7.1.6 of RFC 6455:
            https://www.rfc-editor.org/rfc/rfc6455.html#section-7.1.6

        :obj:`None` if the connection isn't closed yet.

        """
        if self.state is not State.CLOSED:
            return None
        elif self.close_rcvd is None:
            return ""
        else:
            return self.close_rcvd.reason

    async def __aiter__(self) -> AsyncIterator[Data]:
        """
        Iterate on incoming messages.

        The iterator  exits normally when the connection is closed with the
        close code 1000 (OK) or 1001(going away). It raises
        a :exc:`~websockets.exceptions.ConnectionClosedError` exception when
        the connection is closed with any other code.

        """
        try:
            while True:
                yield await self.recv()
        except ConnectionClosedOK:
            return

    async def recv(self) -> Data:
        """
        Receive the next message.

        When the connection is closed, :meth:`recv` raises
        :exc:`~websockets.exceptions.ConnectionClosed`. Specifically, it
        raises :exc:`~websockets.exceptions.ConnectionClosedOK` after a normal
        connection closure and
        :exc:`~websockets.exceptions.ConnectionClosedError` after a protocol
        error or a network failure. This is how you detect the end of the
        message stream.

        Canceling :meth:`recv` is safe. There's no risk of losing the next
        message. The next invocation of :meth:`recv` will return it.

        This makes it possible to enforce a timeout by wrapping :meth:`recv`
        in :func:`~asyncio.wait_for`.

        Returns:
            Data: A string (:class:`str`) for a Text_ frame. A bytestring
            (:class:`bytes`) for a Binary_ frame.

            .. _Text: https://www.rfc-editor.org/rfc/rfc6455.html#section-5.6
            .. _Binary: https://www.rfc-editor.org/rfc/rfc6455.html#section-5.6

        Raises:
            ConnectionClosed: when the connection is closed.
            RuntimeError: if two coroutines call :meth:`recv` concurrently.

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
        self,
        message: Union[Data, Iterable[Data], AsyncIterable[Data]],
    ) -> None:
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
        (If you want to send the keys of a dict-like object as fragments, call
        its :meth:`~dict.keys` method and pass the result to :meth:`send`.)

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
            message (Union[Data, Iterable[Data], AsyncIterable[Data]): message
                to send.

        Raises:
            ConnectionClosed: when the connection is closed.
            TypeError: if ``message`` doesn't have a supported type.

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
            raise TypeError("data must be str, bytes-like, or iterable")

    async def close(self, code: int = 1000, reason: str = "") -> None:
        """
        Perform the closing handshake.

        :meth:`close` waits for the other end to complete the handshake and
        for the TCP connection to terminate. As a consequence, there's no need
        to await :meth:`wait_closed` after :meth:`close`.

        :meth:`close` is idempotent: it doesn't do anything once the
        connection is closed.

        Wrapping :func:`close` in :func:`~asyncio.create_task` is safe, given
        that errors during connection termination aren't particularly useful.

        Canceling :meth:`close` is discouraged. If it takes too long, you can
        set a shorter ``close_timeout``. If you don't want to wait, let the
        Python process exit, then the OS will take care of closing the TCP
        connection.

        Args:
            code: WebSocket close code.
            reason: WebSocket close reason.

        """
        try:
            await asyncio.wait_for(
                self.write_close_frame(Close(code, reason)),
                self.close_timeout,
                **loop_if_py_lt_38(self.loop),
            )  # type: ignore  # remove when removing loop_if_py_lt_38
        except asyncio.TimeoutError:
            # If the close frame cannot be sent because the send buffers
            # are full, the closing handshake won't complete anyway.
            # Fail the connection to shut down faster.
            self.fail_connection()

        # If no close frame is received within the timeout, wait_for() cancels
        # the data transfer task and raises TimeoutError.

        # If close() is called multiple times concurrently and one of these
        # calls hits the timeout, the data transfer task will be canceled.
        # Other calls will receive a CancelledError here.

        try:
            # If close() is canceled during the wait, self.transfer_data_task
            # is canceled before the timeout elapses.
            await asyncio.wait_for(
                self.transfer_data_task,
                self.close_timeout,
                **loop_if_py_lt_38(self.loop),
            )  # type: ignore  # remove when removing loop_if_py_lt_38
        except (asyncio.TimeoutError, asyncio.CancelledError):
            pass

        # Wait for the close connection task to close the TCP connection.
        await asyncio.shield(self.close_connection_task)

    async def wait_closed(self) -> None:
        """
        Wait until the connection is closed.

        This coroutine is identical to the :attr:`closed` attribute, except it
        can be awaited.

        This can make it easier to detect connection termination, regardless
        of its cause, in tasks that interact with the WebSocket connection.

        """
        await asyncio.shield(self.connection_lost_waiter)

    async def ping(self, data: Optional[Data] = None) -> Awaitable[None]:
        """
        Send a Ping_.

        .. _Ping: https://www.rfc-editor.org/rfc/rfc6455.html#section-5.5.2

        A ping may serve as a keepalive or as a check that the remote endpoint
        received all messages up to this point

        Canceling :meth:`ping` is discouraged. If :meth:`ping` doesn't return
        immediately, it means the write buffer is full. If you don't want to
        wait, you should close the connection.

        Canceling the :class:`~asyncio.Future` returned by :meth:`ping` has no
        effect.

        Args:
            data (Optional[Data]): payload of the ping; a string will be
                encoded to UTF-8; or :obj:`None` to generate a payload
                containing four random bytes.

        Returns:
            ~asyncio.Future: A future that will be completed when the
            corresponding pong is received. You can ignore it if you
            don't intend to wait.

            ::

                pong_waiter = await ws.ping()
                await pong_waiter  # only if you want to wait for the pong

        Raises:
            ConnectionClosed: when the connection is closed.
            RuntimeError: if another ping was sent with the same data and
                the corresponding pong wasn't received yet.

        """
        await self.ensure_open()

        if data is not None:
            data = prepare_ctrl(data)

        # Protect against duplicates if a payload is explicitly set.
        if data in self.pings:
            raise RuntimeError("already waiting for a pong with the same data")

        # Generate a unique random payload otherwise.
        while data is None or data in self.pings:
            data = struct.pack("!I", random.getrandbits(32))

        self.pings[data] = self.loop.create_future()

        await self.write_frame(True, OP_PING, data)

        return asyncio.shield(self.pings[data])

    async def pong(self, data: Data = b"") -> None:
        """
        Send a Pong_.

        .. _Pong: https://www.rfc-editor.org/rfc/rfc6455.html#section-5.5.3

        An unsolicited pong may serve as a unidirectional heartbeat.

        Canceling :meth:`pong` is discouraged. If :meth:`pong` doesn't return
        immediately, it means the write buffer is full. If you don't want to
        wait, you should close the connection.

        Args:
            data (Data): payload of the pong; a string will be encoded to
                UTF-8.

        Raises:
            ConnectionClosed: when the connection is closed.

        """
        await self.ensure_open()

        data = prepare_ctrl(data)

        await self.write_frame(True, OP_PONG, data)

    # Private methods - no guarantees.

    def connection_closed_exc(self) -> ConnectionClosed:
        exc: ConnectionClosed
        if (
            self.close_rcvd is not None
            and self.close_rcvd.code in OK_CLOSE_CODES
            and self.close_sent is not None
            and self.close_sent.code in OK_CLOSE_CODES
        ):
            exc = ConnectionClosedOK(
                self.close_rcvd,
                self.close_sent,
                self.close_rcvd_then_sent,
            )
        else:
            exc = ConnectionClosedError(
                self.close_rcvd,
                self.close_sent,
                self.close_rcvd_then_sent,
            )
        # Chain to the exception that terminated data transfer, if any.
        exc.__cause__ = self.transfer_data_exc
        return exc

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

        Return :obj:`None` when the closing handshake is started.

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

        Return :obj:`None` if a close frame is encountered before any data frame.

        """
        # 6.2. Receiving Data
        while True:
            frame = await self.read_frame(max_size)

            # 5.5. Control Frames
            if frame.opcode == OP_CLOSE:
                # 7.1.5.  The WebSocket Connection Close Code
                # 7.1.6.  The WebSocket Connection Close Reason
                self.close_rcvd = Close.parse(frame.data)
                if self.close_sent is not None:
                    self.close_rcvd_then_sent = False
                try:
                    # Echo the original data instead of re-serializing it with
                    # Close.serialize() because that fails when the close frame
                    # is empty and Close.parse() synthetizes a 1005 close code.
                    await self.write_close_frame(self.close_rcvd, frame.data)
                except ConnectionClosed:
                    # Connection closed before we could echo the close frame.
                    pass
                return None

            elif frame.opcode == OP_PING:
                # Answer pings, unless connection is CLOSING.
                if self.state is State.OPEN:
                    try:
                        await self.pong(frame.data)
                    except ConnectionClosed:
                        # Connection closed while draining write buffer.
                        pass

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

    def write_frame_sync(self, fin: bool, opcode: int, data: bytes) -> None:
        frame = Frame(fin, Opcode(opcode), data)
        if self.debug:
            self.logger.debug("> %s", frame)
        frame.write(
            self.transport.write,
            mask=self.is_client,
            extensions=self.extensions,
        )

    async def drain(self) -> None:
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

    async def write_frame(
        self, fin: bool, opcode: int, data: bytes, *, _state: int = State.OPEN
    ) -> None:
        # Defensive assertion for protocol compliance.
        if self.state is not _state:  # pragma: no cover
            raise InvalidState(
                f"Cannot write to a WebSocket in the {self.state.name} state"
            )
        self.write_frame_sync(fin, opcode, data)
        await self.drain()

    async def write_close_frame(
        self, close: Close, data: Optional[bytes] = None
    ) -> None:
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

            self.close_sent = close
            if self.close_rcvd is not None:
                self.close_rcvd_then_sent = True
            if data is None:
                data = close.serialize()

            # 7.1.2. Start the WebSocket Closing Handshake
            await self.write_frame(True, OP_CLOSE, data, _state=State.CLOSING)

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

                self.logger.debug("% sending keepalive ping")
                pong_waiter = await self.ping()

                if self.ping_timeout is not None:
                    try:
                        await asyncio.wait_for(
                            pong_waiter,
                            self.ping_timeout,
                            **loop_if_py_lt_38(self.loop),
                        )  # type: ignore  # remove when removing loop_if_py_lt_38
                        self.logger.debug("% received keepalive pong")
                    except asyncio.TimeoutError:
                        if self.debug:
                            self.logger.debug("! timed out waiting for keepalive pong")
                        self.fail_connection(1011, "keepalive ping timeout")
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

        Return :obj:`True` if the connection is closed and :obj:`False`
        otherwise.

        """
        if not self.connection_lost_waiter.done():
            try:
                await asyncio.wait_for(
                    asyncio.shield(self.connection_lost_waiter),
                    self.close_timeout,
                    **loop_if_py_lt_38(self.loop),
                )  # type: ignore  # remove when removing loop_if_py_lt_38
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
            close = Close(code, reason)

            # Write the close frame without draining the write buffer.

            # Keeping fail_connection() synchronous guarantees it can't
            # get stuck and simplifies the implementation of the callers.
            # Not drainig the write buffer is acceptable in this context.

            # This duplicates a few lines of code from write_close_frame().

            self.state = State.CLOSING
            if self.debug:
                self.logger.debug("= connection is CLOSING")

            # If self.close_rcvd was set, the connection state would be
            # CLOSING. Therefore self.close_rcvd isn't set and we don't
            # have to set self.close_rcvd_then_sent.
            assert self.close_rcvd is None
            self.close_sent = close

            self.write_frame_sync(True, OP_CLOSE, close.serialize())

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
        self.logger.debug("= connection is CLOSED")

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
        there's no reason to keep the transport open by returning :obj:`True`.

        Besides, that doesn't work on TLS connections.

        """
        self.reader.feed_eof()


def broadcast(websockets: Iterable[WebSocketCommonProtocol], message: Data) -> None:
    """
    Broadcast a message to several WebSocket connections.

    A string (:class:`str`) is sent as a Text_ frame. A bytestring or
    bytes-like object (:class:`bytes`, :class:`bytearray`, or
    :class:`memoryview`) is sent as a Binary_ frame.

    .. _Text: https://www.rfc-editor.org/rfc/rfc6455.html#section-5.6
    .. _Binary: https://www.rfc-editor.org/rfc/rfc6455.html#section-5.6

    :func:`broadcast` pushes the message synchronously to all connections even
    if their write buffers are overflowing. There's no backpressure.

    :func:`broadcast` skips silently connections that aren't open in order to
    avoid errors on connections where the closing handshake is in progress.

    If you broadcast messages faster than a connection can handle them,
    messages will pile up in its write buffer until the connection times out.
    Keep low values for ``ping_interval`` and ``ping_timeout`` to prevent
    excessive memory usage by slow connections when you use :func:`broadcast`.

    Unlike :meth:`~websockets.server.WebSocketServerProtocol.send`,
    :func:`broadcast` doesn't support sending fragmented messages. Indeed,
    fragmentation is useful for sending large messages without buffering
    them in memory, while :func:`broadcast` buffers one copy per connection
    as fast as possible.

    Args:
        websockets (Iterable[WebSocketCommonProtocol]): WebSocket connections
            to which the message will be sent.
        message (Data): message to send.

    Raises:
        RuntimeError: if a connection is busy sending a fragmented message.
        TypeError: if ``message`` doesn't have a supported type.

    """
    if not isinstance(message, (str, bytes, bytearray, memoryview)):
        raise TypeError("data must be str or bytes-like")

    opcode, data = prepare_data(message)

    for websocket in websockets:
        if websocket.state is not State.OPEN:
            continue

        if websocket._fragmented_message_waiter is not None:
            raise RuntimeError("busy sending a fragmented message")

        websocket.write_frame_sync(True, opcode, data)
