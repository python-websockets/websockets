from __future__ import annotations

import asyncio
import http
import logging
import socket
from types import TracebackType
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    Generator,
    Iterable,
    Optional,
    Sequence,
    Type,
    Union,
)

from websockets.frames import CloseCode

from ..extensions.base import ServerExtensionFactory
from ..extensions.permessage_deflate import enable_server_permessage_deflate
from ..headers import validate_subprotocols
from ..http import USER_AGENT
from ..http11 import Request, Response
from ..protocol import CONNECTING, Event
from ..server import ServerProtocol
from ..typing import LoggerLike, Origin, Subprotocol
from .compatibility import asyncio_timeout
from .connection import Connection


__all__ = ["serve", "unix_serve", "ServerConnection", "WebSocketServer"]


class ServerConnection(Connection):
    """
    :mod:`asyncio` implementation of a WebSocket server connection.

    :class:`ServerConnection` provides :meth:`recv` and :meth:`send` methods for
    receiving and sending messages.

    It supports asynchronous iteration to receive messages::

        async for message in websocket:
            await process(message)

    The iterator exits normally when the connection is closed with close code
    1000 (OK) or 1001 (going away) or without a close code. It raises a
    :exc:`~websockets.exceptions.ConnectionClosedError` when the connection is
    closed with any other code.

    Args:
        protocol: Sans-I/O connection.
        server: :class:`WebSocketServer` that created this connection.
        close_timeout: Timeout for closing connections in seconds.
            :obj:`None` disables the timeout.

    """

    def __init__(
        self,
        protocol: ServerProtocol,
        server: WebSocketServer,
        *,
        close_timeout: Optional[float] = 10,
    ) -> None:
        self.protocol: ServerProtocol
        super().__init__(
            protocol,
            close_timeout=close_timeout,
        )
        self.server = server
        self.request_rcvd: asyncio.Future[None] = self.loop.create_future()

    async def handshake(
        self,
        process_request: Optional[
            Callable[
                [ServerConnection, Request],
                Union[Optional[Response], Awaitable[Optional[Response]]],
            ]
        ] = None,
        process_response: Optional[
            Callable[
                [ServerConnection, Request, Response],
                Union[Optional[Response], Awaitable[Optional[Response]]],
            ]
        ] = None,
        server_header: Optional[str] = USER_AGENT,
    ) -> None:
        """
        Perform the opening handshake.

        """
        # May raise CancelledError if open_timeout is exceeded.
        await self.request_rcvd

        if self.request is None:
            raise ConnectionError("connection closed during handshake")

        async with self.send_context(expected_state=CONNECTING):
            response = None

            if process_request is not None:
                try:
                    response = process_request(self, self.request)
                    if isinstance(response, Awaitable):
                        response = await response
                except Exception as exc:
                    self.protocol.handshake_exc = exc
                    self.logger.error("opening handshake failed", exc_info=True)
                    response = self.protocol.reject(
                        http.HTTPStatus.INTERNAL_SERVER_ERROR,
                        (
                            "Failed to open a WebSocket connection.\n"
                            "See server log for more information.\n"
                        ),
                    )

            if response is None:
                self.response = self.protocol.accept(self.request)
            else:
                assert isinstance(response, Response)  # help mypy
                self.response = response

            if server_header is not None:
                self.response.headers["Server"] = server_header

            response = None

            if process_response is not None:
                try:
                    response = process_response(self, self.request, self.response)
                    if isinstance(response, Awaitable):
                        response = await response
                except Exception as exc:
                    self.protocol.handshake_exc = exc
                    self.logger.error("opening handshake failed", exc_info=True)
                    response = self.protocol.reject(
                        http.HTTPStatus.INTERNAL_SERVER_ERROR,
                        (
                            "Failed to open a WebSocket connection.\n"
                            "See server log for more information.\n"
                        ),
                    )

            if response is not None:
                assert isinstance(response, Response)  # help mypy
                self.response = response

            self.protocol.send_response(self.response)

        if self.protocol.handshake_exc is not None:
            try:
                async with asyncio_timeout(self.close_timeout):
                    await self.connection_lost_waiter
            finally:
                raise self.protocol.handshake_exc

    def process_event(self, event: Event) -> None:
        """
        Process one incoming event.

        """
        # First event - handshake request.
        if self.request is None:
            assert isinstance(event, Request)
            self.request = event
            self.request_rcvd.set_result(None)
        # Later events - frames.
        else:
            super().process_event(event)

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        super().connection_made(transport)
        self.server.start_connection_handler(self)

    def connection_lost(self, exc: Optional[Exception]) -> None:
        try:
            super().connection_lost(exc)
        finally:
            # If the connection is closed during the handshake, unblock it.
            if not self.request_rcvd.done():
                self.request_rcvd.set_result(None)


class WebSocketServer:
    """
    WebSocket server returned by :func:`serve`.

    This class mirrors the API of :class:`~asyncio.Server`.

    It keeps track of WebSocket connections in order to close them properly
    when shutting down.

    Args:
        handler: Connection handler. It receives the WebSocket connection,
            which is a :class:`ServerConnection`, in argument.
        process_request: Intercept the request during the opening handshake.
            Return an HTTP response to force the response or :obj:`None` to
            continue normally. When you force an HTTP 101 Continue response, the
            handshake is successful. Else, the connection is aborted.
            ``process_request`` may be a function or a coroutine.
        process_response: Intercept the response during the opening handshake.
            Return an HTTP response to force the response or :obj:`None` to
            continue normally. When you force an HTTP 101 Continue response, the
            handshake is successful. Else, the connection is aborted.
            ``process_response`` may be a function or a coroutine.
        server_header: Value of  the ``Server`` response header.
            It defaults to ``"Python/x.y.z websockets/X.Y"``. Setting it to
            :obj:`None` removes the header.
        open_timeout: Timeout for opening connections in seconds.
            :obj:`None` disables the timeout.
        logger: Logger for this server.
            It defaults to ``logging.getLogger("websockets.server")``.
            See the :doc:`logging guide <../../topics/logging>` for details.

    """

    def __init__(
        self,
        handler: Callable[[ServerConnection], Awaitable[None]],
        *,
        process_request: Optional[
            Callable[
                [ServerConnection, Request],
                Union[Optional[Response], Awaitable[Optional[Response]]],
            ]
        ] = None,
        process_response: Optional[
            Callable[
                [ServerConnection, Request, Response],
                Union[Optional[Response], Awaitable[Optional[Response]]],
            ]
        ] = None,
        server_header: Optional[str] = USER_AGENT,
        open_timeout: Optional[float] = 10,
        logger: Optional[LoggerLike] = None,
    ):
        self.loop = asyncio.get_running_loop()
        self.handler = handler
        self.process_request = process_request
        self.process_response = process_response
        self.server_header = server_header
        self.open_timeout = open_timeout
        if logger is None:
            logger = logging.getLogger("websockets.server")
        self.logger = logger

        # Keep track of active connections.
        self.connections: Dict[ServerConnection, asyncio.Task[None]] = {}

        # Task responsible for closing the server and terminating connections.
        self.close_task: Optional[asyncio.Task[None]] = None

        # Completed when the server is closed and connections are terminated.
        self.closed_waiter: asyncio.Future[None]

    def wrap(self, server: asyncio.Server) -> None:
        """
        Attach to a given :class:`~asyncio.Server`.

        Since :meth:`~asyncio.loop.create_server` doesn't support injecting a
        custom ``Server`` class, the easiest solution that doesn't rely on
        private :mod:`asyncio` APIs is to:

        - instantiate a :class:`WebSocketServer`
        - give the protocol factory a reference to that instance
        - call :meth:`~asyncio.loop.create_server` with the factory
        - attach the resulting :class:`~asyncio.Server` with this method

        """
        self.server = server
        for sock in server.sockets:
            if sock.family == socket.AF_INET:
                name = "%s:%d" % sock.getsockname()
            elif sock.family == socket.AF_INET6:
                name = "[%s]:%d" % sock.getsockname()[:2]
            elif sock.family == socket.AF_UNIX:
                name = sock.getsockname()
            # In the unlikely event that someone runs websockets over a
            # protocol other than IP or Unix sockets, avoid crashing.
            else:  # pragma: no cover
                name = str(sock.getsockname())
            self.logger.info("server listening on %s", name)

        # Initialized here because we need a reference to the event loop.
        # This should be moved back to __init__ when dropping Python < 3.10.
        self.closed_waiter = server.get_loop().create_future()

    async def conn_handler(self, connection: ServerConnection) -> None:
        """
        Handle the lifecycle of a WebSocket connection.

        Since this method doesn't have a caller that can handle exceptions,
        it attempts to log relevant ones.

        It guarantees that the TCP connection is closed before exiting.

        """
        try:
            # On failure, handshake() closes the transport, raises an
            # exception, and logs it.
            async with asyncio_timeout(self.open_timeout):
                await connection.handshake(
                    self.process_request,
                    self.process_response,
                    self.server_header,
                )

            try:
                await self.handler(connection)
            except Exception:
                self.logger.error("connection handler failed", exc_info=True)
                await connection.close(CloseCode.INTERNAL_ERROR)
            else:
                await connection.close()

        except Exception:
            # Don't leak connections on errors.
            connection.transport.abort()

        finally:
            # Registration is tied to the lifecycle of conn_handler() because
            # the server waits for connection handlers to terminate, even if
            # all connections are already closed.
            del self.connections[connection]

    def start_connection_handler(self, connection: ServerConnection) -> None:
        """
        Register a connection with this server.

        """
        # The connection must be registered in self.connections immediately.
        # If it was registered in conn_handler(), a race condition would be
        # possible when closing the server after scheduling conn_handler()
        # but before it starts executing.
        self.connections[connection] = self.loop.create_task(
            self.conn_handler(connection)
        )

    def close(self, close_connections: bool = True) -> None:
        """
        Close the server.

        * Close the underlying :class:`~asyncio.Server`.
        * When ``close_connections`` is :obj:`True`, which is the default,
          close existing connections. Specifically:

          * Reject opening WebSocket connections with an HTTP 503 (service
            unavailable) error. This happens when the server accepted the TCP
            connection but didn't complete the opening handshake before closing.
          * Close open WebSocket connections with close code 1001 (going away).

        * Wait until all connection handlers terminate.

        :meth:`close` is idempotent.

        """
        if self.close_task is None:
            self.close_task = self.get_loop().create_task(
                self._close(close_connections)
            )

    async def _close(self, close_connections: bool) -> None:
        """
        Implementation of :meth:`close`.

        This calls :meth:`~asyncio.Server.close` on the underlying
        :class:`~asyncio.Server` object to stop accepting new connections and
        then closes open connections with close code 1001.

        """
        self.logger.info("server closing")

        # Stop accepting new connections.
        self.server.close()

        # Wait until all accepted connections reach connection_made() and call
        # register(). See https://bugs.python.org/issue34852 for details.
        await asyncio.sleep(0)

        if close_connections:
            # Close OPEN connections with close code 1001. After server.close(),
            # handshake() closes OPENING connections with an HTTP 503 error.
            close_tasks = [
                asyncio.create_task(connection.close(1001))
                for connection in self.connections
                if connection.protocol.state is not CONNECTING
            ]
            # asyncio.wait doesn't accept an empty first argument.
            if close_tasks:
                await asyncio.wait(close_tasks)

        # Wait until all TCP connections are closed.
        await self.server.wait_closed()

        # Wait until all connection handlers terminate.
        # asyncio.wait doesn't accept an empty first argument.
        if self.connections:
            await asyncio.wait(self.connections.values())

        # Tell wait_closed() to return.
        self.closed_waiter.set_result(None)

        self.logger.info("server closed")

    async def wait_closed(self) -> None:
        """
        Wait until the server is closed.

        When :meth:`wait_closed` returns, all TCP connections are closed and
        all connection handlers have returned.

        To ensure a fast shutdown, a connection handler should always be
        awaiting at least one of:

        * :meth:`~WebSocketServerProtocol.recv`: when the connection is closed,
          it raises :exc:`~websockets.exceptions.ConnectionClosedOK`;
        * :meth:`~WebSocketServerProtocol.wait_closed`: when the connection is
          closed, it returns.

        Then the connection handler is immediately notified of the shutdown;
        it can clean up and exit.

        """
        await asyncio.shield(self.closed_waiter)

    def get_loop(self) -> asyncio.AbstractEventLoop:
        """
        See :meth:`asyncio.Server.get_loop`.

        """
        return self.server.get_loop()

    def is_serving(self) -> bool:  # pragma: no cover
        """
        See :meth:`asyncio.Server.is_serving`.

        """
        return self.server.is_serving()

    async def start_serving(self) -> None:  # pragma: no cover
        """
        See :meth:`asyncio.Server.start_serving`.

        Typical use::

            server = await serve(..., start_serving=False)
            # perform additional setup here...
            # ... then start the server
            await server.start_serving()

        """
        await self.server.start_serving()

    async def serve_forever(self) -> None:  # pragma: no cover
        """
        See :meth:`asyncio.Server.serve_forever`.

        Typical use::

            server = await serve(...)
            # this coroutine doesn't return
            # canceling it stops the server
            await server.serve_forever()

        This is an alternative to using :func:`serve` as an asynchronous context
        manager. Shutdown is triggered by canceling :meth:`serve_forever`
        instead of exiting a :func:`serve` context.

        """
        await self.server.serve_forever()

    @property
    def sockets(self) -> Iterable[socket.socket]:
        """
        See :attr:`asyncio.Server.sockets`.

        """
        return self.server.sockets

    async def __aenter__(self) -> WebSocketServer:  # pragma: no cover
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:  # pragma: no cover
        self.close()
        await self.wait_closed()


class serve:
    """
    Create a WebSocket server listening on ``host`` and ``port``.

    Whenever a client connects, the server creates a :class:`ServerConnection`,
    performs the opening handshake, and delegates to the ``handler``.

    The handler receives the :class:`ServerConnection` instance, which you can
    use to send and receive messages.

    Once the handler completes, either normally or with an exception, the server
    performs the closing handshake and closes the connection.

    This coroutine returns a :class:`WebSocketServer` whose API mirrors
    :class:`~asyncio.Server`. Treat it as an asynchronous context manager to
    ensure that it will be closed::

        def handler(websocket):
            ...

        # set this future to exit the server stop =
        asyncio.get_running_loop().create_future()

        async with websockets.asyncio.server.serve(handler, host, port):
            await stop

    Alternatively, call :meth:`~WebSocketServer.serve_forever` to serve requests
    and cancel it to stop the server::

        server = await websockets.asyncio.server.serve(handler, host, port)
        await server.serve_forever()

    Args:
        handler: Connection handler. It receives the WebSocket connection,
            which is a :class:`ServerConnection`, in argument.
        host: Network interfaces the server binds to.
            See :meth:`~asyncio.loop.create_server` for details.
        port: TCP port the server listens on.
            See :meth:`~asyncio.loop.create_server` for details.
        origins: Acceptable values of the ``Origin`` header, for defending
            against Cross-Site WebSocket Hijacking attacks. Include :obj:`None`
            in the list if the lack of an origin is acceptable.
        extensions: List of supported extensions, in order in which they
            should be negotiated and run.
        subprotocols: List of supported subprotocols, in order of decreasing
            preference.
        select_subprotocol: Callback for selecting a subprotocol among
            those supported by the client and the server. It receives a
            :class:`ServerConnection` (not a
            :class:`~websockets.server.ServerProtocol`!) instance and a list of
            subprotocols offered by the client. Other than the first argument,
            it has the same behavior as the
            :meth:`ServerProtocol.select_subprotocol
            <websockets.server.ServerProtocol.select_subprotocol>` method.
        process_request: Intercept the request during the opening handshake.
            Return an HTTP response to force the response or :obj:`None` to
            continue normally. When you force an HTTP 101 Continue response, the
            handshake is successful. Else, the connection is aborted.
            ``process_request`` may be a function or a coroutine.
        process_response: Intercept the response during the opening handshake.
            Return an HTTP response to force the response or :obj:`None` to
            continue normally. When you force an HTTP 101 Continue response, the
            handshake is successful. Else, the connection is aborted.
            ``process_response`` may be a function or a coroutine.
        server_header: Value of  the ``Server`` response header.
            It defaults to ``"Python/x.y.z websockets/X.Y"``. Setting it to
            :obj:`None` removes the header.
        compression: The "permessage-deflate" extension is enabled by default.
            Set ``compression`` to :obj:`None` to disable it. See the
            :doc:`compression guide <../../topics/compression>` for details.
        open_timeout: Timeout for opening connections in seconds.
            :obj:`None` disables the timeout.
        close_timeout: Timeout for closing connections in seconds.
            :obj:`None` disables the timeout.
        max_size: Maximum size of incoming messages in bytes.
            :obj:`None` disables the limit.
        logger: Logger for this server.
            It defaults to ``logging.getLogger("websockets.server")``. See the
            :doc:`logging guide <../../topics/logging>` for details.
        create_connection: Factory for the :class:`ServerConnection` managing
            the connection. Set it to a wrapper or a subclass to customize
            connection handling.

    Any other keyword arguments are passed to the event loop's
    :meth:`~asyncio.loop.create_server` method.

    For example:

    * You can set ``ssl`` to a :class:`~ssl.SSLContext` to enable TLS.

    * You can set ``sock`` to provide a preexisting TCP socket. You may call
      :func:`socket.create_server` (not to be confused with the event loop's
      :meth:`~asyncio.loop.create_server` method) to create a suitable client
      socket and customize it.

    * You can set ``start_serving`` to ``False`` to start accepting connections
      only after you call :meth:`~WebSocketServer.start_serving()` or
      :meth:`~WebSocketServer.serve_forever()`.

    """

    def __init__(
        self,
        handler: Callable[[ServerConnection], Awaitable[None]],
        host: Optional[str] = None,
        port: Optional[int] = None,
        *,
        # WebSocket
        origins: Optional[Sequence[Optional[Origin]]] = None,
        extensions: Optional[Sequence[ServerExtensionFactory]] = None,
        subprotocols: Optional[Sequence[Subprotocol]] = None,
        select_subprotocol: Optional[
            Callable[
                [ServerConnection, Sequence[Subprotocol]],
                Optional[Subprotocol],
            ]
        ] = None,
        process_request: Optional[
            Callable[
                [ServerConnection, Request],
                Optional[Response],
            ]
        ] = None,
        process_response: Optional[
            Callable[
                [ServerConnection, Request, Response],
                Optional[Response],
            ]
        ] = None,
        server_header: Optional[str] = USER_AGENT,
        compression: Optional[str] = "deflate",
        # Timeouts
        open_timeout: Optional[float] = 10,
        close_timeout: Optional[float] = 10,
        # Limits
        max_size: Optional[int] = 2**20,
        # Logging
        logger: Optional[LoggerLike] = None,
        # Escape hatch for advanced customization
        create_connection: Optional[Type[ServerConnection]] = None,
        # Other keyword arguments are passed to loop.create_server
        **kwargs: Any,
    ) -> None:

        if subprotocols is not None:
            validate_subprotocols(subprotocols)

        if compression == "deflate":
            extensions = enable_server_permessage_deflate(extensions)
        elif compression is not None:
            raise ValueError(f"unsupported compression: {compression}")

        if create_connection is None:
            create_connection = ServerConnection

        self.server = WebSocketServer(
            handler,
            process_request=process_request,
            process_response=process_response,
            server_header=server_header,
            open_timeout=open_timeout,
            logger=logger,
        )

        if kwargs.get("ssl") is not None:
            kwargs.setdefault("ssl_handshake_timeout", open_timeout)
            kwargs.setdefault("ssl_shutdown_timeout", close_timeout)

        def factory() -> ServerConnection:
            """
            Create an asyncio protocol for managing a WebSocket connection.

            """
            # Create a closure to give select_subprotocol access to connection.
            protocol_select_subprotocol: Optional[
                Callable[
                    [ServerProtocol, Sequence[Subprotocol]],
                    Optional[Subprotocol],
                ]
            ] = None
            if select_subprotocol is not None:

                def protocol_select_subprotocol(
                    protocol: ServerProtocol,
                    subprotocols: Sequence[Subprotocol],
                ) -> Optional[Subprotocol]:
                    # mypy doesn't know that select_subprotocol is immutable.
                    assert select_subprotocol is not None
                    # Ensure this function is only used in the intended context.
                    assert protocol is connection.protocol
                    return select_subprotocol(connection, subprotocols)

            # This is a protocol in websockets.
            protocol = ServerProtocol(
                origins=origins,
                extensions=extensions,
                subprotocols=subprotocols,
                select_subprotocol=protocol_select_subprotocol,
                max_size=max_size,
                logger=logger,
            )
            # This is a connection in websockets and a protocol in asyncio.
            connection = create_connection(
                protocol,
                self.server,
                close_timeout=close_timeout,
            )
            return connection

        loop = asyncio.get_running_loop()
        if kwargs.pop("unix", False):
            self._create_server = loop.create_unix_server(factory, **kwargs)
        else:
            # mypy cannot tell that kwargs must provide sock when port is None.
            self._create_server = loop.create_server(factory, host, port, **kwargs)  # type: ignore[arg-type]

    # async with serve(...) as ...: ...

    async def __aenter__(self) -> WebSocketServer:
        return await self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        self.server.close()
        await self.server.wait_closed()

    # ... = await serve(...)

    def __await__(self) -> Generator[Any, None, WebSocketServer]:
        # Create a suitable iterator by calling __await__ on a coroutine.
        return self.__await_impl__().__await__()

    async def __await_impl__(self) -> WebSocketServer:
        server = await self._create_server
        self.server.wrap(server)
        return self.server

    # ... = yield from serve(...) - remove when dropping Python < 3.10

    __iter__ = __await__


def unix_serve(
    handler: Callable[[ServerConnection], Awaitable[None]],
    path: Optional[str] = None,
    **kwargs: Any,
) -> Awaitable[WebSocketServer]:
    """
    Create a WebSocket server listening on a Unix socket.

    This function is identical to :func:`serve`, except the ``host`` and
    ``port`` arguments are replaced by ``path``. It's only available on Unix.

    It's useful for deploying a server behind a reverse proxy such as nginx.

    Args:
        handler: Connection handler. It receives the WebSocket connection,
            which is a :class:`ServerConnection`, in argument.
        path: File system path to the Unix socket.

    """
    return serve(handler, unix=True, path=path, **kwargs)
