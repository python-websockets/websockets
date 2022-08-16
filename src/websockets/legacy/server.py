from __future__ import annotations

import asyncio
import email.utils
import functools
import http
import inspect
import logging
import socket
import warnings
from types import TracebackType
from typing import (
    Any,
    Awaitable,
    Callable,
    Generator,
    Iterable,
    List,
    Optional,
    Sequence,
    Set,
    Tuple,
    Type,
    Union,
    cast,
)

from ..connection import State
from ..datastructures import Headers, HeadersLike, MultipleValuesError
from ..exceptions import (
    AbortHandshake,
    InvalidHandshake,
    InvalidHeader,
    InvalidMessage,
    InvalidOrigin,
    InvalidUpgrade,
    NegotiationError,
)
from ..extensions import Extension, ServerExtensionFactory
from ..extensions.permessage_deflate import enable_server_permessage_deflate
from ..headers import (
    build_extension,
    parse_extension,
    parse_subprotocol,
    validate_subprotocols,
)
from ..http import USER_AGENT
from ..typing import ExtensionHeader, LoggerLike, Origin, Subprotocol
from .compatibility import loop_if_py_lt_38
from .handshake import build_response, check_request
from .http import read_request
from .protocol import WebSocketCommonProtocol


__all__ = ["serve", "unix_serve", "WebSocketServerProtocol", "WebSocketServer"]


HeadersLikeOrCallable = Union[HeadersLike, Callable[[str, Headers], HeadersLike]]

HTTPResponse = Tuple[http.HTTPStatus, HeadersLike, bytes]


class WebSocketServerProtocol(WebSocketCommonProtocol):
    """
    WebSocket server connection.

    :class:`WebSocketServerProtocol` provides :meth:`recv` and :meth:`send`
    coroutines for receiving and sending messages.

    It supports asynchronous iteration to receive messages::

        async for message in websocket:
            await process(message)

    The iterator exits normally when the connection is closed with close code
    1000 (OK) or 1001 (going away). It raises
    a :exc:`~websockets.exceptions.ConnectionClosedError` when the connection
    is closed with any other code.

    You may customize the opening handshake in a subclass by
    overriding :meth:`process_request` or :meth:`select_subprotocol`.

    Args:
        ws_server: WebSocket server that created this connection.

    See :func:`serve` for the documentation of ``ws_handler``, ``logger``, ``origins``,
    ``extensions``, ``subprotocols``, and ``extra_headers``.

    See :class:`~websockets.legacy.protocol.WebSocketCommonProtocol` for the
    documentation of ``ping_interval``, ``ping_timeout``, ``close_timeout``,
    ``max_size``, ``max_queue``, ``read_limit``, and ``write_limit``.

    """

    is_client = False
    side = "server"

    def __init__(
        self,
        ws_handler: Union[
            Callable[[WebSocketServerProtocol], Awaitable[Any]],
            Callable[[WebSocketServerProtocol, str], Awaitable[Any]],  # deprecated
        ],
        ws_server: WebSocketServer,
        *,
        logger: Optional[LoggerLike] = None,
        origins: Optional[Sequence[Optional[Origin]]] = None,
        extensions: Optional[Sequence[ServerExtensionFactory]] = None,
        subprotocols: Optional[Sequence[Subprotocol]] = None,
        extra_headers: Optional[HeadersLikeOrCallable] = None,
        process_request: Optional[
            Callable[[str, Headers], Awaitable[Optional[HTTPResponse]]]
        ] = None,
        select_subprotocol: Optional[
            Callable[[Sequence[Subprotocol], Sequence[Subprotocol]], Subprotocol]
        ] = None,
        no_server_header: bool = False,
        **kwargs: Any,
    ) -> None:
        if logger is None:
            logger = logging.getLogger("websockets.server")
        super().__init__(logger=logger, **kwargs)
        # For backwards compatibility with 6.0 or earlier.
        if origins is not None and "" in origins:
            warnings.warn("use None instead of '' in origins", DeprecationWarning)
            origins = [None if origin == "" else origin for origin in origins]
        # For backwards compatibility with 10.0 or earlier. Done here in
        # addition to serve to trigger the deprecation warning on direct
        # use of WebSocketServerProtocol.
        self.ws_handler = remove_path_argument(ws_handler)
        self.ws_server = ws_server
        self.origins = origins
        self.available_extensions = extensions
        self.available_subprotocols = subprotocols
        self.extra_headers = extra_headers
        self._process_request = process_request
        self._select_subprotocol = select_subprotocol
        self.no_server_header = no_server_header

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        """
        Register connection and initialize a task to handle it.

        """
        super().connection_made(transport)
        # Register the connection with the server before creating the handler
        # task. Registering at the beginning of the handler coroutine would
        # create a race condition between the creation of the task, which
        # schedules its execution, and the moment the handler starts running.
        self.ws_server.register(self)
        self.handler_task = self.loop.create_task(self.handler())

    async def handler(self) -> None:
        """
        Handle the lifecycle of a WebSocket connection.

        Since this method doesn't have a caller able to handle exceptions, it
        attempts to log relevant ones and guarantees that the TCP connection is
        closed before exiting.

        """
        try:

            try:
                await self.handshake(
                    origins=self.origins,
                    available_extensions=self.available_extensions,
                    available_subprotocols=self.available_subprotocols,
                    extra_headers=self.extra_headers,
                )
            # Remove this branch when dropping support for Python < 3.8
            # because CancelledError no longer inherits Exception.
            except asyncio.CancelledError:  # pragma: no cover
                raise
            except ConnectionError:
                raise
            except Exception as exc:
                if isinstance(exc, AbortHandshake):
                    status, headers, body = exc.status, exc.headers, exc.body
                elif isinstance(exc, InvalidOrigin):
                    if self.debug:
                        self.logger.debug("! invalid origin", exc_info=True)
                    status, headers, body = (
                        http.HTTPStatus.FORBIDDEN,
                        Headers(),
                        f"Failed to open a WebSocket connection: {exc}.\n".encode(),
                    )
                elif isinstance(exc, InvalidUpgrade):
                    if self.debug:
                        self.logger.debug("! invalid upgrade", exc_info=True)
                    status, headers, body = (
                        http.HTTPStatus.UPGRADE_REQUIRED,
                        Headers([("Upgrade", "websocket")]),
                        (
                            f"Failed to open a WebSocket connection: {exc}.\n"
                            f"\n"
                            f"You cannot access a WebSocket server directly "
                            f"with a browser. You need a WebSocket client.\n"
                        ).encode(),
                    )
                elif isinstance(exc, InvalidHandshake):
                    if self.debug:
                        self.logger.debug("! invalid handshake", exc_info=True)
                    status, headers, body = (
                        http.HTTPStatus.BAD_REQUEST,
                        Headers(),
                        f"Failed to open a WebSocket connection: {exc}.\n".encode(),
                    )
                else:
                    self.logger.error("opening handshake failed", exc_info=True)
                    status, headers, body = (
                        http.HTTPStatus.INTERNAL_SERVER_ERROR,
                        Headers(),
                        (
                            b"Failed to open a WebSocket connection.\n"
                            b"See server log for more information.\n"
                        ),
                    )

                headers.setdefault("Date", email.utils.formatdate(usegmt=True))
                if not self.no_server_header:
                    headers.setdefault("Server", USER_AGENT)
                headers.setdefault("Content-Length", str(len(body)))
                headers.setdefault("Content-Type", "text/plain")
                headers.setdefault("Connection", "close")

                self.write_http_response(status, headers, body)
                self.logger.info(
                    "connection failed (%d %s)", status.value, status.phrase
                )
                await self.close_transport()
                return

            try:
                await self.ws_handler(self)
            except Exception:
                self.logger.error("connection handler failed", exc_info=True)
                if not self.closed:
                    self.fail_connection(1011)
                raise

            try:
                await self.close()
            except ConnectionError:
                raise
            except Exception:
                self.logger.error("closing handshake failed", exc_info=True)
                raise

        except Exception:
            # Last-ditch attempt to avoid leaking connections on errors.
            try:
                self.transport.close()
            except Exception:  # pragma: no cover
                pass

        finally:
            # Unregister the connection with the server when the handler task
            # terminates. Registration is tied to the lifecycle of the handler
            # task because the server waits for tasks attached to registered
            # connections before terminating.
            self.ws_server.unregister(self)
            self.logger.info("connection closed")

    async def read_http_request(self) -> Tuple[str, Headers]:
        """
        Read request line and headers from the HTTP request.

        If the request contains a body, it may be read from ``self.reader``
        after this coroutine returns.

        Raises:
            InvalidMessage: if the HTTP message is malformed or isn't an
                HTTP/1.1 GET request.

        """
        try:
            path, headers = await read_request(self.reader)
        except asyncio.CancelledError:  # pragma: no cover
            raise
        except Exception as exc:
            raise InvalidMessage("did not receive a valid HTTP request") from exc

        if self.debug:
            self.logger.debug("< GET %s HTTP/1.1", path)
            for key, value in headers.raw_items():
                self.logger.debug("< %s: %s", key, value)

        self.path = path
        self.request_headers = headers

        return path, headers

    def write_http_response(
        self, status: http.HTTPStatus, headers: Headers, body: Optional[bytes] = None
    ) -> None:
        """
        Write status line and headers to the HTTP response.

        This coroutine is also able to write a response body.

        """
        self.response_headers = headers

        if self.debug:
            self.logger.debug("> HTTP/1.1 %d %s", status.value, status.phrase)
            for key, value in headers.raw_items():
                self.logger.debug("> %s: %s", key, value)
            if body is not None:
                self.logger.debug("> [body] (%d bytes)", len(body))

        # Since the status line and headers only contain ASCII characters,
        # we can keep this simple.
        response = f"HTTP/1.1 {status.value} {status.phrase}\r\n"
        response += str(headers)

        self.transport.write(response.encode())

        if body is not None:
            self.transport.write(body)

    async def process_request(
        self, path: str, request_headers: Headers
    ) -> Optional[HTTPResponse]:
        """
        Intercept the HTTP request and return an HTTP response if appropriate.

        You may override this method in a :class:`WebSocketServerProtocol`
        subclass, for example:

        * to return a HTTP 200 OK response on a given path; then a load
          balancer can use this path for a health check;
        * to authenticate the request and return a HTTP 401 Unauthorized or a
          HTTP 403 Forbidden when authentication fails.

        You may also override this method with the ``process_request``
        argument of :func:`serve` and :class:`WebSocketServerProtocol`. This
        is equivalent, except ``process_request`` won't have access to the
        protocol instance, so it can't store information for later use.

        :meth:`process_request` is expected to complete quickly. If it may run
        for a long time, then it should await :meth:`wait_closed` and exit if
        :meth:`wait_closed` completes, or else it could prevent the server
        from shutting down.

        Args:
            path: request path, including optional query string.
            request_headers: request headers.

        Returns:
            Optional[Tuple[http.HTTPStatus, HeadersLike, bytes]]: :obj:`None`
            to continue the WebSocket handshake normally.

            An HTTP response, represented by a 3-uple of the response status,
            headers, and body, to abort the WebSocket handshake and return
            that HTTP response instead.

        """
        if self._process_request is not None:
            response = self._process_request(path, request_headers)
            if isinstance(response, Awaitable):
                return await response
            else:
                # For backwards compatibility with 7.0.
                warnings.warn(
                    "declare process_request as a coroutine", DeprecationWarning
                )
                return response
        return None

    @staticmethod
    def process_origin(
        headers: Headers, origins: Optional[Sequence[Optional[Origin]]] = None
    ) -> Optional[Origin]:
        """
        Handle the Origin HTTP request header.

        Args:
            headers: request headers.
            origins: optional list of acceptable origins.

        Raises:
            InvalidOrigin: if the origin isn't acceptable.

        """
        # "The user agent MUST NOT include more than one Origin header field"
        # per https://www.rfc-editor.org/rfc/rfc6454.html#section-7.3.
        try:
            origin = cast(Optional[Origin], headers.get("Origin"))
        except MultipleValuesError as exc:
            raise InvalidHeader("Origin", "more than one Origin header found") from exc
        if origins is not None:
            if origin not in origins:
                raise InvalidOrigin(origin)
        return origin

    @staticmethod
    def process_extensions(
        headers: Headers,
        available_extensions: Optional[Sequence[ServerExtensionFactory]],
    ) -> Tuple[Optional[str], List[Extension]]:
        """
        Handle the Sec-WebSocket-Extensions HTTP request header.

        Accept or reject each extension proposed in the client request.
        Negotiate parameters for accepted extensions.

        Return the Sec-WebSocket-Extensions HTTP response header and the list
        of accepted extensions.

        :rfc:`6455` leaves the rules up to the specification of each
        :extension.

        To provide this level of flexibility, for each extension proposed by
        the client, we check for a match with each extension available in the
        server configuration. If no match is found, the extension is ignored.

        If several variants of the same extension are proposed by the client,
        it may be accepted several times, which won't make sense in general.
        Extensions must implement their own requirements. For this purpose,
        the list of previously accepted extensions is provided.

        This process doesn't allow the server to reorder extensions. It can
        only select a subset of the extensions proposed by the client.

        Other requirements, for example related to mandatory extensions or the
        order of extensions, may be implemented by overriding this method.

        Args:
            headers: request headers.
            extensions: optional list of supported extensions.

        Raises:
            InvalidHandshake: to abort the handshake with an HTTP 400 error.

        """
        response_header_value: Optional[str] = None

        extension_headers: List[ExtensionHeader] = []
        accepted_extensions: List[Extension] = []

        header_values = headers.get_all("Sec-WebSocket-Extensions")

        if header_values and available_extensions:

            parsed_header_values: List[ExtensionHeader] = sum(
                [parse_extension(header_value) for header_value in header_values], []
            )

            for name, request_params in parsed_header_values:

                for ext_factory in available_extensions:

                    # Skip non-matching extensions based on their name.
                    if ext_factory.name != name:
                        continue

                    # Skip non-matching extensions based on their params.
                    try:
                        response_params, extension = ext_factory.process_request_params(
                            request_params, accepted_extensions
                        )
                    except NegotiationError:
                        continue

                    # Add matching extension to the final list.
                    extension_headers.append((name, response_params))
                    accepted_extensions.append(extension)

                    # Break out of the loop once we have a match.
                    break

                # If we didn't break from the loop, no extension in our list
                # matched what the client sent. The extension is declined.

        # Serialize extension header.
        if extension_headers:
            response_header_value = build_extension(extension_headers)

        return response_header_value, accepted_extensions

    # Not @staticmethod because it calls self.select_subprotocol()
    def process_subprotocol(
        self, headers: Headers, available_subprotocols: Optional[Sequence[Subprotocol]]
    ) -> Optional[Subprotocol]:
        """
        Handle the Sec-WebSocket-Protocol HTTP request header.

        Return Sec-WebSocket-Protocol HTTP response header, which is the same
        as the selected subprotocol.

        Args:
            headers: request headers.
            available_subprotocols: optional list of supported subprotocols.

        Raises:
            InvalidHandshake: to abort the handshake with an HTTP 400 error.

        """
        subprotocol: Optional[Subprotocol] = None

        header_values = headers.get_all("Sec-WebSocket-Protocol")

        if header_values and available_subprotocols:

            parsed_header_values: List[Subprotocol] = sum(
                [parse_subprotocol(header_value) for header_value in header_values], []
            )

            subprotocol = self.select_subprotocol(
                parsed_header_values, available_subprotocols
            )

        return subprotocol

    def select_subprotocol(
        self,
        client_subprotocols: Sequence[Subprotocol],
        server_subprotocols: Sequence[Subprotocol],
    ) -> Optional[Subprotocol]:
        """
        Pick a subprotocol among those offered by the client.

        If several subprotocols are supported by the client and the server,
        the default implementation selects the preferred subprotocol by
        giving equal value to the priorities of the client and the server.
        If no subprotocol is supported by the client and the server, it
        proceeds without a subprotocol.

        This is unlikely to be the most useful implementation in practice.
        Many servers providing a subprotocol will require that the client
        uses that subprotocol. Such rules can be implemented in a subclass.

        You may also override this method with the ``select_subprotocol``
        argument of :func:`serve` and :class:`WebSocketServerProtocol`.

        Args:
            client_subprotocols: list of subprotocols offered by the client.
            server_subprotocols: list of subprotocols available on the server.

        Returns:
            Optional[Subprotocol]: Selected subprotocol.

            :obj:`None` to continue without a subprotocol.


        """
        if self._select_subprotocol is not None:
            return self._select_subprotocol(client_subprotocols, server_subprotocols)

        subprotocols = set(client_subprotocols) & set(server_subprotocols)
        if not subprotocols:
            return None
        priority = lambda p: (
            client_subprotocols.index(p) + server_subprotocols.index(p)
        )
        return sorted(subprotocols, key=priority)[0]

    async def handshake(
        self,
        origins: Optional[Sequence[Optional[Origin]]] = None,
        available_extensions: Optional[Sequence[ServerExtensionFactory]] = None,
        available_subprotocols: Optional[Sequence[Subprotocol]] = None,
        extra_headers: Optional[HeadersLikeOrCallable] = None,
    ) -> str:
        """
        Perform the server side of the opening handshake.

        Args:
            origins: list of acceptable values of the Origin HTTP header;
                include :obj:`None` if the lack of an origin is acceptable.
            extensions: list of supported extensions, in order in which they
                should be tried.
            subprotocols: list of supported subprotocols, in order of
                decreasing preference.
            extra_headers: arbitrary HTTP headers to add to the response when
                the handshake succeeds.

        Returns:
            str: path of the URI of the request.

        Raises:
            InvalidHandshake: if the handshake fails.

        """
        path, request_headers = await self.read_http_request()

        # Hook for customizing request handling, for example checking
        # authentication or treating some paths as plain HTTP endpoints.
        early_response_awaitable = self.process_request(path, request_headers)
        if isinstance(early_response_awaitable, Awaitable):
            early_response = await early_response_awaitable
        else:
            # For backwards compatibility with 7.0.
            warnings.warn("declare process_request as a coroutine", DeprecationWarning)
            early_response = early_response_awaitable

        # The connection may drop while process_request is running.
        if self.state is State.CLOSED:
            raise self.connection_closed_exc()  # pragma: no cover

        # Change the response to a 503 error if the server is shutting down.
        if not self.ws_server.is_serving():
            early_response = (
                http.HTTPStatus.SERVICE_UNAVAILABLE,
                [],
                b"Server is shutting down.\n",
            )

        if early_response is not None:
            raise AbortHandshake(*early_response)

        key = check_request(request_headers)

        self.origin = self.process_origin(request_headers, origins)

        extensions_header, self.extensions = self.process_extensions(
            request_headers, available_extensions
        )

        protocol_header = self.subprotocol = self.process_subprotocol(
            request_headers, available_subprotocols
        )

        response_headers = Headers()

        build_response(response_headers, key)

        if extensions_header is not None:
            response_headers["Sec-WebSocket-Extensions"] = extensions_header

        if protocol_header is not None:
            response_headers["Sec-WebSocket-Protocol"] = protocol_header

        if callable(extra_headers):
            extra_headers = extra_headers(path, self.request_headers)
        if extra_headers is not None:
            response_headers.update(extra_headers)

        response_headers.setdefault("Date", email.utils.formatdate(usegmt=True))
        if not self.no_server_header:
            response_headers.setdefault("Server", USER_AGENT)

        self.write_http_response(http.HTTPStatus.SWITCHING_PROTOCOLS, response_headers)

        self.logger.info("connection open")

        self.connection_open()

        return path


class WebSocketServer:
    """
    WebSocket server returned by :func:`serve`.

    This class provides the same interface as :class:`~asyncio.Server`,
    notably the :meth:`~asyncio.Server.close`
    and :meth:`~asyncio.Server.wait_closed` methods.

    It keeps track of WebSocket connections in order to close them properly
    when shutting down.

    Args:
        logger: logger for this server;
            defaults to ``logging.getLogger("websockets.server")``;
            see the :doc:`logging guide <../topics/logging>` for details.

    """

    def __init__(self, logger: Optional[LoggerLike] = None):
        if logger is None:
            logger = logging.getLogger("websockets.server")
        self.logger = logger

        # Keep track of active connections.
        self.websockets: Set[WebSocketServerProtocol] = set()

        # Task responsible for closing the server and terminating connections.
        self.close_task: Optional[asyncio.Task[None]] = None

        # Completed when the server is closed and connections are terminated.
        self.closed_waiter: asyncio.Future[None]

    def wrap(self, server: asyncio.base_events.Server) -> None:
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
        # This should be moved back to __init__ in Python 3.10.
        self.closed_waiter = server.get_loop().create_future()

    def register(self, protocol: WebSocketServerProtocol) -> None:
        """
        Register a connection with this server.

        """
        self.websockets.add(protocol)

    def unregister(self, protocol: WebSocketServerProtocol) -> None:
        """
        Unregister a connection with this server.

        """
        self.websockets.remove(protocol)

    def close(self) -> None:
        """
        Close the server.

        This method:

        * closes the underlying :class:`~asyncio.Server`;
        * rejects new WebSocket connections with an HTTP 503 (service
          unavailable) error; this happens when the server accepted the TCP
          connection but didn't complete the WebSocket opening handshake prior
          to closing;
        * closes open WebSocket connections with close code 1001 (going away).

        :meth:`close` is idempotent.

        """
        if self.close_task is None:
            self.close_task = self.get_loop().create_task(self._close())

    async def _close(self) -> None:
        """
        Implementation of :meth:`close`.

        This calls :meth:`~asyncio.Server.close` on the underlying
        :class:`~asyncio.Server` object to stop accepting new connections and
        then closes open connections with close code 1001.

        """
        self.logger.info("server closing")

        # Stop accepting new connections.
        self.server.close()

        # Wait until self.server.close() completes.
        await self.server.wait_closed()

        # Wait until all accepted connections reach connection_made() and call
        # register(). See https://bugs.python.org/issue34852 for details.
        await asyncio.sleep(0, **loop_if_py_lt_38(self.get_loop()))

        # Close OPEN connections with status code 1001. Since the server was
        # closed, handshake() closes OPENING connections with a HTTP 503
        # error. Wait until all connections are closed.

        close_tasks = [
            asyncio.create_task(websocket.close(1001))
            for websocket in self.websockets
            if websocket.state is not State.CONNECTING
        ]
        # asyncio.wait doesn't accept an empty first argument.
        if close_tasks:
            await asyncio.wait(
                close_tasks,
                **loop_if_py_lt_38(self.get_loop()),
            )

        # Wait until all connection handlers are complete.

        # asyncio.wait doesn't accept an empty first argument.
        if self.websockets:
            await asyncio.wait(
                [websocket.handler_task for websocket in self.websockets],
                **loop_if_py_lt_38(self.get_loop()),
            )

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

    def is_serving(self) -> bool:
        """
        See :meth:`asyncio.Server.is_serving`.

        """
        return self.server.is_serving()

    async def start_serving(self) -> None:
        """
        See :meth:`asyncio.Server.start_serving`.

        Typical use::

            server = await serve(..., start_serving=False)
            # perform additional setup here...
            # ... then start the server
            await server.start_serving()

        """
        await self.server.start_serving()  # pragma: no cover

    async def serve_forever(self) -> None:
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
        await self.server.serve_forever()  # pragma: no cover

    @property
    def sockets(self) -> Iterable[socket.socket]:
        """
        See :attr:`asyncio.Server.sockets`.

        """
        return self.server.sockets

    async def __aenter__(self) -> WebSocketServer:
        return self  # pragma: no cover

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        self.close()  # pragma: no cover
        await self.wait_closed()  # pragma: no cover


class Serve:
    """
    Start a WebSocket server listening on ``host`` and ``port``.

    Whenever a client connects, the server creates a
    :class:`WebSocketServerProtocol`, performs the opening handshake, and
    delegates to the connection handler, ``ws_handler``.

    The handler receives the :class:`WebSocketServerProtocol` and uses it to
    send and receive messages.

    Once the handler completes, either normally or with an exception, the
    server performs the closing handshake and closes the connection.

    Awaiting :func:`serve` yields a :class:`WebSocketServer`. This object
    provides :meth:`~WebSocketServer.close` and
    :meth:`~WebSocketServer.wait_closed` methods for shutting down the server.

    :func:`serve` can be used as an asynchronous context manager::

        stop = asyncio.Future()  # set this future to exit the server

        async with serve(...):
            await stop

    The server is shut down automatically when exiting the context.

    Args:
        ws_handler: connection handler. It receives the WebSocket connection,
            which is a :class:`WebSocketServerProtocol`, in argument.
        host: network interfaces the server is bound to;
            see :meth:`~asyncio.loop.create_server` for details.
        port: TCP port the server listens on;
            see :meth:`~asyncio.loop.create_server` for details.
        create_protocol: factory for the :class:`asyncio.Protocol` managing
            the connection; defaults to :class:`WebSocketServerProtocol`; may
            be set to a wrapper or a subclass to customize connection handling.
        logger: logger for this server;
            defaults to ``logging.getLogger("websockets.server")``;
            see the :doc:`logging guide <../topics/logging>` for details.
        compression: shortcut that enables the "permessage-deflate" extension
            by default; may be set to :obj:`None` to disable compression;
            see the :doc:`compression guide <../topics/compression>` for details.
        origins: acceptable values of the ``Origin`` header; include
            :obj:`None` in the list if the lack of an origin is acceptable.
            This is useful for defending against Cross-Site WebSocket
            Hijacking attacks.
        extensions: list of supported extensions, in order in which they
            should be tried.
        subprotocols: list of supported subprotocols, in order of decreasing
            preference.
        extra_headers (Union[HeadersLike, Callable[[str, Headers], HeadersLike]]):
            arbitrary HTTP headers to add to the request; this can be
            a :data:`~websockets.datastructures.HeadersLike` or a callable
            taking the request path and headers in arguments and returning
            a :data:`~websockets.datastructures.HeadersLike`.
        process_request (Optional[Callable[[str, Headers], \
            Awaitable[Optional[Tuple[http.HTTPStatus, HeadersLike, bytes]]]]]):
            intercept HTTP request before the opening handshake;
            see :meth:`~WebSocketServerProtocol.process_request` for details.
        select_subprotocol: select a subprotocol supported by the client;
            see :meth:`~WebSocketServerProtocol.select_subprotocol` for details.

    See :class:`~websockets.legacy.protocol.WebSocketCommonProtocol` for the
    documentation of ``ping_interval``, ``ping_timeout``, ``close_timeout``,
    ``max_size``, ``max_queue``, ``read_limit``, and ``write_limit``.

    Any other keyword arguments are passed the event loop's
    :meth:`~asyncio.loop.create_server` method.

    For example:

    * You can set ``ssl`` to a :class:`~ssl.SSLContext` to enable TLS.

    * You can set ``sock`` to a :obj:`~socket.socket` that you created
      outside of websockets.

    Returns:
        WebSocketServer: WebSocket server.

    """

    def __init__(
        self,
        ws_handler: Union[
            Callable[[WebSocketServerProtocol], Awaitable[Any]],
            Callable[[WebSocketServerProtocol, str], Awaitable[Any]],  # deprecated
        ],
        host: Optional[Union[str, Sequence[str]]] = None,
        port: Optional[int] = None,
        *,
        create_protocol: Optional[Callable[[Any], WebSocketServerProtocol]] = None,
        logger: Optional[LoggerLike] = None,
        compression: Optional[str] = "deflate",
        origins: Optional[Sequence[Optional[Origin]]] = None,
        extensions: Optional[Sequence[ServerExtensionFactory]] = None,
        subprotocols: Optional[Sequence[Subprotocol]] = None,
        extra_headers: Optional[HeadersLikeOrCallable] = None,
        process_request: Optional[
            Callable[[str, Headers], Awaitable[Optional[HTTPResponse]]]
        ] = None,
        select_subprotocol: Optional[
            Callable[[Sequence[Subprotocol], Sequence[Subprotocol]], Subprotocol]
        ] = None,
        ping_interval: Optional[float] = 20,
        ping_timeout: Optional[float] = 20,
        close_timeout: Optional[float] = None,
        max_size: Optional[int] = 2**20,
        max_queue: Optional[int] = 2**5,
        read_limit: int = 2**16,
        write_limit: int = 2**16,
        **kwargs: Any,
    ) -> None:
        # Backwards compatibility: close_timeout used to be called timeout.
        timeout: Optional[float] = kwargs.pop("timeout", None)
        if timeout is None:
            timeout = 10
        else:
            warnings.warn("rename timeout to close_timeout", DeprecationWarning)
        # If both are specified, timeout is ignored.
        if close_timeout is None:
            close_timeout = timeout

        # Backwards compatibility: create_protocol used to be called klass.
        klass: Optional[Type[WebSocketServerProtocol]] = kwargs.pop("klass", None)
        if klass is None:
            klass = WebSocketServerProtocol
        else:
            warnings.warn("rename klass to create_protocol", DeprecationWarning)
        # If both are specified, klass is ignored.
        if create_protocol is None:
            create_protocol = klass

        # Backwards compatibility: recv() used to return None on closed connections
        legacy_recv: bool = kwargs.pop("legacy_recv", False)

        # Backwards compatibility: the loop parameter used to be supported.
        _loop: Optional[asyncio.AbstractEventLoop] = kwargs.pop("loop", None)
        if _loop is None:
            loop = asyncio.get_event_loop()
        else:
            loop = _loop
            warnings.warn("remove loop argument", DeprecationWarning)

        ws_server = WebSocketServer(logger=logger)

        secure = kwargs.get("ssl") is not None

        if compression == "deflate":
            extensions = enable_server_permessage_deflate(extensions)
        elif compression is not None:
            raise ValueError(f"unsupported compression: {compression}")

        if subprotocols is not None:
            validate_subprotocols(subprotocols)

        factory = functools.partial(
            create_protocol,
            # For backwards compatibility with 10.0 or earlier. Done here in
            # addition to WebSocketServerProtocol to trigger the deprecation
            # warning once per serve() call rather than once per connection.
            remove_path_argument(ws_handler),
            ws_server,
            host=host,
            port=port,
            secure=secure,
            ping_interval=ping_interval,
            ping_timeout=ping_timeout,
            close_timeout=close_timeout,
            max_size=max_size,
            max_queue=max_queue,
            read_limit=read_limit,
            write_limit=write_limit,
            loop=_loop,
            legacy_recv=legacy_recv,
            origins=origins,
            extensions=extensions,
            subprotocols=subprotocols,
            extra_headers=extra_headers,
            process_request=process_request,
            select_subprotocol=select_subprotocol,
            logger=logger,
        )

        if kwargs.pop("unix", False):
            path: Optional[str] = kwargs.pop("path", None)
            # unix_serve(path) must not specify host and port parameters.
            assert host is None and port is None
            create_server = functools.partial(
                loop.create_unix_server, factory, path, **kwargs
            )
        else:
            create_server = functools.partial(
                loop.create_server, factory, host, port, **kwargs
            )

        # This is a coroutine function.
        self._create_server = create_server
        self.ws_server = ws_server

    # async with serve(...)

    async def __aenter__(self) -> WebSocketServer:
        return await self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        self.ws_server.close()
        await self.ws_server.wait_closed()

    # await serve(...)

    def __await__(self) -> Generator[Any, None, WebSocketServer]:
        # Create a suitable iterator by calling __await__ on a coroutine.
        return self.__await_impl__().__await__()

    async def __await_impl__(self) -> WebSocketServer:
        server = await self._create_server()
        self.ws_server.wrap(server)
        return self.ws_server

    # yield from serve(...) - remove when dropping Python < 3.10

    __iter__ = __await__


serve = Serve


def unix_serve(
    ws_handler: Union[
        Callable[[WebSocketServerProtocol], Awaitable[Any]],
        Callable[[WebSocketServerProtocol, str], Awaitable[Any]],  # deprecated
    ],
    path: Optional[str] = None,
    **kwargs: Any,
) -> Serve:
    """
    Similar to :func:`serve`, but for listening on Unix sockets.

    This function builds upon the event
    loop's :meth:`~asyncio.loop.create_unix_server` method.

    It is only available on Unix.

    It's useful for deploying a server behind a reverse proxy such as nginx.

    Args:
        path: file system path to the Unix socket.

    """
    return serve(ws_handler, path=path, unix=True, **kwargs)


def remove_path_argument(
    ws_handler: Union[
        Callable[[WebSocketServerProtocol], Awaitable[Any]],
        Callable[[WebSocketServerProtocol, str], Awaitable[Any]],
    ]
) -> Callable[[WebSocketServerProtocol], Awaitable[Any]]:
    try:
        inspect.signature(ws_handler).bind(None)
    except TypeError:
        try:
            inspect.signature(ws_handler).bind(None, "")
        except TypeError:  # pragma: no cover
            # ws_handler accepts neither one nor two arguments; leave it alone.
            pass
        else:
            # ws_handler accepts two arguments; activate backwards compatibility.

            # Enable deprecation warning and announce deprecation in 11.0.
            # warnings.warn("remove second argument of ws_handler", DeprecationWarning)

            async def _ws_handler(websocket: WebSocketServerProtocol) -> Any:
                return await cast(
                    Callable[[WebSocketServerProtocol, str], Awaitable[Any]],
                    ws_handler,
                )(websocket, websocket.path)

            return _ws_handler

    return cast(
        Callable[[WebSocketServerProtocol], Awaitable[Any]],
        ws_handler,
    )
