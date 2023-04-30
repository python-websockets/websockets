from __future__ import annotations

import http
import logging
import os
import selectors
import socket
import ssl
import sys
import threading
from types import TracebackType
from typing import Any, Callable, Optional, Sequence, Type

from ..extensions.base import ServerExtensionFactory
from ..extensions.permessage_deflate import enable_server_permessage_deflate
from ..headers import validate_subprotocols
from ..http import USER_AGENT
from ..http11 import Request, Response
from ..protocol import CONNECTING, OPEN, Event
from ..server import ServerProtocol
from ..typing import LoggerLike, Origin, Subprotocol
from .connection import Connection
from .utils import Deadline


__all__ = ["serve", "unix_serve", "ServerConnection", "WebSocketServer"]


class ServerConnection(Connection):
    """
    Threaded implementation of a WebSocket server connection.

    :class:`ServerConnection` provides :meth:`recv` and :meth:`send` methods for
    receiving and sending messages.

    It supports iteration to receive messages::

        for message in websocket:
            process(message)

    The iterator exits normally when the connection is closed with close code
    1000 (OK) or 1001 (going away) or without a close code. It raises a
    :exc:`~websockets.exceptions.ConnectionClosedError` when the connection is
    closed with any other code.

    Args:
        socket: Socket connected to a WebSocket client.
        protocol: Sans-I/O connection.
        close_timeout: Timeout for closing the connection in seconds.

    """

    def __init__(
        self,
        socket: socket.socket,
        protocol: ServerProtocol,
        *,
        close_timeout: Optional[float] = 10,
    ) -> None:
        self.protocol: ServerProtocol
        self.request_rcvd = threading.Event()
        super().__init__(
            socket,
            protocol,
            close_timeout=close_timeout,
        )

    def handshake(
        self,
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
        timeout: Optional[float] = None,
    ) -> None:
        """
        Perform the opening handshake.

        """
        if not self.request_rcvd.wait(timeout):
            self.close_socket()
            self.recv_events_thread.join()
            raise TimeoutError("timed out during handshake")

        if self.request is None:
            self.close_socket()
            self.recv_events_thread.join()
            raise ConnectionError("connection closed during handshake")

        with self.send_context(expected_state=CONNECTING):
            self.response = None

            if process_request is not None:
                try:
                    self.response = process_request(self, self.request)
                except Exception as exc:
                    self.protocol.handshake_exc = exc
                    self.logger.error("opening handshake failed", exc_info=True)
                    self.response = self.protocol.reject(
                        http.HTTPStatus.INTERNAL_SERVER_ERROR,
                        (
                            "Failed to open a WebSocket connection.\n"
                            "See server log for more information.\n"
                        ),
                    )

            if self.response is None:
                self.response = self.protocol.accept(self.request)

            if server_header is not None:
                self.response.headers["Server"] = server_header

            if process_response is not None:
                try:
                    response = process_response(self, self.request, self.response)
                except Exception as exc:
                    self.protocol.handshake_exc = exc
                    self.logger.error("opening handshake failed", exc_info=True)
                    self.response = self.protocol.reject(
                        http.HTTPStatus.INTERNAL_SERVER_ERROR,
                        (
                            "Failed to open a WebSocket connection.\n"
                            "See server log for more information.\n"
                        ),
                    )
                else:
                    if response is not None:
                        self.response = response

            self.protocol.send_response(self.response)

        if self.protocol.state is not OPEN:
            self.recv_events_thread.join(self.close_timeout)
            self.close_socket()
            self.recv_events_thread.join()

        if self.protocol.handshake_exc is not None:
            raise self.protocol.handshake_exc

    def process_event(self, event: Event) -> None:
        """
        Process one incoming event.

        """
        # First event - handshake request.
        if self.request is None:
            assert isinstance(event, Request)
            self.request = event
            self.request_rcvd.set()
        # Later events - frames.
        else:
            super().process_event(event)

    def recv_events(self) -> None:
        """
        Read incoming data from the socket and process events.

        """
        try:
            super().recv_events()
        finally:
            # If the connection is closed during the handshake, unblock it.
            self.request_rcvd.set()


class WebSocketServer:
    """
    WebSocket server returned by :func:`serve`.

    This class mirrors the API of :class:`~socketserver.BaseServer`, notably the
    :meth:`~socketserver.BaseServer.serve_forever` and
    :meth:`~socketserver.BaseServer.shutdown` methods, as well as the context
    manager protocol.

    Args:
        socket: Server socket listening for new connections.
        handler: Handler for one connection. Receives the socket and address
            returned by :meth:`~socket.socket.accept`.
        logger: Logger for this server.

    """

    def __init__(
        self,
        socket: socket.socket,
        handler: Callable[[socket.socket, Any], None],
        logger: Optional[LoggerLike] = None,
    ):
        self.socket = socket
        self.handler = handler
        if logger is None:
            logger = logging.getLogger("websockets.server")
        self.logger = logger
        if sys.platform != "win32":
            self.shutdown_watcher, self.shutdown_notifier = os.pipe()

    def serve_forever(self) -> None:
        """
        See :meth:`socketserver.BaseServer.serve_forever`.

        This method doesn't return. Calling :meth:`shutdown` from another thread
        stops the server.

        Typical use::

            with serve(...) as server:
                server.serve_forever()

        """
        poller = selectors.DefaultSelector()
        poller.register(self.socket, selectors.EVENT_READ)
        if sys.platform != "win32":
            poller.register(self.shutdown_watcher, selectors.EVENT_READ)

        while True:
            poller.select()
            try:
                # If the socket is closed, this will raise an exception and exit
                # the loop. So we don't need to check the return value of select().
                sock, addr = self.socket.accept()
            except OSError:
                break
            thread = threading.Thread(target=self.handler, args=(sock, addr))
            thread.start()

    def shutdown(self) -> None:
        """
        See :meth:`socketserver.BaseServer.shutdown`.

        """
        self.socket.close()
        if sys.platform != "win32":
            os.write(self.shutdown_notifier, b"x")

    def fileno(self) -> int:
        """
        See :meth:`socketserver.BaseServer.fileno`.

        """
        return self.socket.fileno()

    def __enter__(self) -> WebSocketServer:
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        self.shutdown()


def serve(
    handler: Callable[[ServerConnection], None],
    host: Optional[str] = None,
    port: Optional[int] = None,
    *,
    # TCP/TLS — unix and path are only for unix_serve()
    sock: Optional[socket.socket] = None,
    ssl_context: Optional[ssl.SSLContext] = None,
    unix: bool = False,
    path: Optional[str] = None,
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
) -> WebSocketServer:
    """
    Create a WebSocket server listening on ``host`` and ``port``.

    Whenever a client connects, the server creates a :class:`ServerConnection`,
    performs the opening handshake, and delegates to the ``handler``.

    The handler receives a :class:`ServerConnection` instance, which you can use
    to send and receive messages.

    Once the handler completes, either normally or with an exception, the server
    performs the closing handshake and closes the connection.

    :class:`WebSocketServer` mirrors the API of
    :class:`~socketserver.BaseServer`. Treat it as a context manager to ensure
    that it will be closed and call the :meth:`~WebSocketServer.serve_forever`
    method to serve requests::

        def handler(websocket):
            ...

        with websockets.sync.server.serve(handler, ...) as server:
            server.serve_forever()

    Args:
        handler: Connection handler. It receives the WebSocket connection,
            which is a :class:`ServerConnection`, in argument.
        host: Network interfaces the server binds to.
            See :func:`~socket.create_server` for details.
        port: TCP port the server listens on.
            See :func:`~socket.create_server` for details.
        sock: Preexisting TCP socket. ``sock`` replaces ``host`` and ``port``.
            You may call :func:`socket.create_server` to create a suitable TCP
            socket.
        ssl_context: Configuration for enabling TLS on the connection.
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
            continue normally. When you force an HTTP 101 Continue response,
            the handshake is successful. Else, the connection is aborted.
        process_response: Intercept the response during the opening handshake.
            Return an HTTP response to force the response or :obj:`None` to
            continue normally. When you force an HTTP 101 Continue response,
            the handshake is successful. Else, the connection is aborted.
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
    """

    # Process parameters

    if subprotocols is not None:
        validate_subprotocols(subprotocols)

    if compression == "deflate":
        extensions = enable_server_permessage_deflate(extensions)
    elif compression is not None:
        raise ValueError(f"unsupported compression: {compression}")

    if create_connection is None:
        create_connection = ServerConnection

    # Bind socket and listen

    if sock is None:
        if unix:
            if path is None:
                raise TypeError("missing path argument")
            sock = socket.create_server(path, family=socket.AF_UNIX)
        else:
            sock = socket.create_server((host, port))
    else:
        if path is not None:
            raise TypeError("path and sock arguments are incompatible")

    # Initialize TLS wrapper

    if ssl_context is not None:
        sock = ssl_context.wrap_socket(
            sock,
            server_side=True,
            # Delay TLS handshake until after we set a timeout on the socket.
            do_handshake_on_connect=False,
        )

    # Define request handler

    def conn_handler(sock: socket.socket, addr: Any) -> None:
        # Calculate timeouts on the TLS and WebSocket handshakes.
        # The TLS timeout must be set on the socket, then removed
        # to avoid conflicting with the WebSocket timeout in handshake().
        deadline = Deadline(open_timeout)

        try:
            # Disable Nagle algorithm

            if not unix:
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, True)

            # Perform TLS handshake

            if ssl_context is not None:
                sock.settimeout(deadline.timeout())
                assert isinstance(sock, ssl.SSLSocket)  # mypy cannot figure this out
                sock.do_handshake()
                sock.settimeout(None)

            # Create a closure so that select_subprotocol has access to self.

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

            # Initialize WebSocket connection

            protocol = ServerProtocol(
                origins=origins,
                extensions=extensions,
                subprotocols=subprotocols,
                select_subprotocol=protocol_select_subprotocol,
                state=CONNECTING,
                max_size=max_size,
                logger=logger,
            )

            # Initialize WebSocket protocol

            assert create_connection is not None  # help mypy
            connection = create_connection(
                sock,
                protocol,
                close_timeout=close_timeout,
            )
            # On failure, handshake() closes the socket, raises an exception, and
            # logs it.
            connection.handshake(
                process_request,
                process_response,
                server_header,
                deadline.timeout(),
            )

        except Exception:
            sock.close()
            return

        try:
            handler(connection)
        except Exception:
            protocol.logger.error("connection handler failed", exc_info=True)
            connection.close(1011)
        else:
            connection.close()

    # Initialize server

    return WebSocketServer(sock, conn_handler, logger)


def unix_serve(
    handler: Callable[[ServerConnection], Any],
    path: Optional[str] = None,
    **kwargs: Any,
) -> WebSocketServer:
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
    return serve(handler, path=path, unix=True, **kwargs)
