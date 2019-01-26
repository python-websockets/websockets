"""
The :mod:`websockets.server` module defines a simple WebSocket server API.

"""

import asyncio
import collections.abc
import email.utils
import http
import logging
import sys
import warnings

from .exceptions import (
    AbortHandshake,
    InvalidHandshake,
    InvalidHeader,
    InvalidMessage,
    InvalidOrigin,
    InvalidUpgrade,
    NegotiationError,
)
from .extensions.permessage_deflate import ServerPerMessageDeflateFactory
from .handshake import build_response, check_request
from .headers import build_extension_list, parse_extension_list, parse_subprotocol_list
from .http import USER_AGENT, Headers, MultipleValuesError, read_request
from .protocol import State, WebSocketCommonProtocol


__all__ = ["serve", "unix_serve", "WebSocketServerProtocol"]

logger = logging.getLogger(__name__)


class WebSocketServerProtocol(WebSocketCommonProtocol):
    """
    Complete WebSocket server implementation as an :class:`asyncio.Protocol`.

    This class inherits most of its methods from
    :class:`~websockets.protocol.WebSocketCommonProtocol`.

    For the sake of simplicity, it doesn't rely on a full HTTP implementation.
    Its support for HTTP responses is very limited.

    """

    is_client = False
    side = "server"

    def __init__(
        self,
        ws_handler,
        ws_server,
        *,
        origins=None,
        extensions=None,
        subprotocols=None,
        extra_headers=None,
        process_request=None,
        select_subprotocol=None,
        **kwds
    ):
        # For backwards-compatibility with 6.0 or earlier.
        if origins is not None and "" in origins:
            warnings.warn("use None instead of '' in origins", DeprecationWarning)
            origins = [None if origin == "" else origin for origin in origins]
        self.ws_handler = ws_handler
        self.ws_server = ws_server
        self.origins = origins
        self.available_extensions = extensions
        self.available_subprotocols = subprotocols
        self.extra_headers = extra_headers
        if process_request is not None:
            self.process_request = process_request
        if select_subprotocol is not None:
            self.select_subprotocol = select_subprotocol
        super().__init__(**kwds)

    def connection_made(self, transport):
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

    async def handler(self):
        """
        Handle the lifecycle of a WebSocket connection.

        Since this method doesn't have a caller able to handle exceptions, it
        attemps to log relevant ones and guarantees that the TCP connection is
        closed before exiting.

        """
        try:

            try:
                path = await self.handshake(
                    origins=self.origins,
                    available_extensions=self.available_extensions,
                    available_subprotocols=self.available_subprotocols,
                    extra_headers=self.extra_headers,
                )
            except ConnectionError:
                logger.debug("Connection error in opening handshake", exc_info=True)
                raise
            except Exception as exc:
                if isinstance(exc, AbortHandshake):
                    status, headers, body = exc.status, exc.headers, exc.body
                elif isinstance(exc, InvalidOrigin):
                    logger.debug("Invalid origin", exc_info=True)
                    status, headers, body = (
                        http.HTTPStatus.FORBIDDEN,
                        [],
                        (str(exc) + "\n").encode(),
                    )
                elif isinstance(exc, InvalidUpgrade):
                    logger.debug("Invalid upgrade", exc_info=True)
                    status, headers, body = (
                        http.HTTPStatus.UPGRADE_REQUIRED,
                        [("Upgrade", "websocket")],
                        (str(exc) + "\n").encode(),
                    )
                elif isinstance(exc, InvalidHandshake):
                    logger.debug("Invalid handshake", exc_info=True)
                    status, headers, body = (
                        http.HTTPStatus.BAD_REQUEST,
                        [],
                        (str(exc) + "\n").encode(),
                    )
                else:
                    logger.warning("Error in opening handshake", exc_info=True)
                    status, headers, body = (
                        http.HTTPStatus.INTERNAL_SERVER_ERROR,
                        [],
                        b"See server log for more information.\n",
                    )

                if not isinstance(headers, Headers):
                    headers = Headers(headers)

                headers.setdefault("Date", email.utils.formatdate(usegmt=True))
                headers.setdefault("Server", USER_AGENT)
                headers.setdefault("Content-Length", str(len(body)))
                headers.setdefault("Content-Type", "text/plain")
                headers.setdefault("Connection", "close")

                self.write_http_response(status, headers, body)
                self.fail_connection()
                await self.wait_closed()
                return

            try:
                await self.ws_handler(self, path)
            except Exception:
                logger.error("Error in connection handler", exc_info=True)
                if not self.closed:
                    self.fail_connection(1011)
                raise

            try:
                await self.close()
            except ConnectionError:
                logger.debug("Connection error in closing handshake", exc_info=True)
                raise
            except Exception:
                logger.warning("Error in closing handshake", exc_info=True)
                raise

        except Exception:
            # Last-ditch attempt to avoid leaking connections on errors.
            try:
                self.writer.close()
            except Exception:  # pragma: no cover
                pass

        finally:
            # Unregister the connection with the server when the handler task
            # terminates. Registration is tied to the lifecycle of the handler
            # task because the server waits for tasks attached to registered
            # connections before terminating.
            self.ws_server.unregister(self)

    async def read_http_request(self):
        """
        Read request line and headers from the HTTP request.

        Raise :exc:`~websockets.exceptions.InvalidMessage` if the HTTP message
        is malformed or isn't an HTTP/1.1 GET request.

        Don't attempt to read the request body because WebSocket handshake
        requests don't have one. If the request contains a body, it may be
        read from ``self.reader`` after this coroutine returns.

        """
        try:
            path, headers = await read_request(self.reader)
        except ValueError as exc:
            raise InvalidMessage("Malformed HTTP message") from exc

        logger.debug("%s < GET %s HTTP/1.1", self.side, path)
        logger.debug("%s < %r", self.side, headers)

        self.path = path
        self.request_headers = headers

        return path, headers

    def write_http_response(self, status, headers, body=None):
        """
        Write status line and headers to the HTTP response.

        This coroutine is also able to write a response body.

        """
        self.response_headers = headers

        logger.debug("%s > HTTP/1.1 %d %s", self.side, status.value, status.phrase)
        logger.debug("%s > %r", self.side, headers)

        # Since the status line and headers only contain ASCII characters,
        # we can keep this simple.
        response = "HTTP/1.1 {status.value} {status.phrase}\r\n".format(status=status)
        response += str(headers)

        self.writer.write(response.encode())

        if body is not None:
            logger.debug("%s > Body (%d bytes)", self.side, len(body))
            self.writer.write(body)

    def process_request(self, path, request_headers):
        """
        Intercept the HTTP request and return an HTTP response if needed.

        ``request_headers`` is a :class:`~websockets.http.Headers` instance.

        If this method returns ``None``, the WebSocket handshake continues.
        If it returns a status code, headers and a response body, that HTTP
        response is sent and the connection is closed.

        The HTTP status must be a :class:`~http.HTTPStatus`.

        HTTP headers must be a :class:`~websockets.http.Headers` instance, a
        :class:`~collections.abc.Mapping`, or an iterable of ``(name, value)``
        pairs.

        The HTTP response body must be :class:`bytes`. It may be empty.

        This method may be overridden to check the request headers and set a
        different status, for example to authenticate the request and return
        ``HTTPStatus.UNAUTHORIZED`` or ``HTTPStatus.FORBIDDEN``.

        It can be declared as a function or as a coroutine because such
        authentication checks are likely to require network requests.

        It may also be overridden by passing a ``process_request`` argument to
        the :class:`WebSocketServerProtocol` constructor or the :func:`serve`
        function.

        """

    @staticmethod
    def process_origin(headers, origins=None):
        """
        Handle the Origin HTTP request header.

        Raise :exc:`~websockets.exceptions.InvalidOrigin` if the origin isn't
        acceptable.

        """
        # "The user agent MUST NOT include more than one Origin header field"
        # per https://tools.ietf.org/html/rfc6454#section-7.3.
        try:
            origin = headers.get("Origin")
        except MultipleValuesError:
            raise InvalidHeader("Origin", "more than one Origin header found")
        if origins is not None:
            if origin not in origins:
                raise InvalidOrigin(origin)
        return origin

    @staticmethod
    def process_extensions(headers, available_extensions):
        """
        Handle the Sec-WebSocket-Extensions HTTP request header.

        Accept or reject each extension proposed in the client request.
        Negotiate parameters for accepted extensions.

        Return the Sec-WebSocket-Extensions HTTP response header and the list
        of accepted extensions.

        Raise :exc:`~websockets.exceptions.InvalidHandshake` to abort the
        handshake with an HTTP 400 error code. (The default implementation
        never does this.)

        :rfc:`6455` leaves the rules up to the specification of each
        :extension.

        To provide this level of flexibility, for each extension proposed by
        the client, we check for a match with each extension available in the
        server configuration. If no match is found, the extension is ignored.

        If several variants of the same extension are proposed by the client,
        it may be accepted severel times, which won't make sense in general.
        Extensions must implement their own requirements. For this purpose,
        the list of previously accepted extensions is provided.

        This process doesn't allow the server to reorder extensions. It can
        only select a subset of the extensions proposed by the client.

        Other requirements, for example related to mandatory extensions or the
        order of extensions, may be implemented by overriding this method.

        """
        response_header = []
        accepted_extensions = []

        header_values = headers.get_all("Sec-WebSocket-Extensions")

        if header_values and available_extensions:

            parsed_header_values = sum(
                [parse_extension_list(header_value) for header_value in header_values],
                [],
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
                    response_header.append((name, response_params))
                    accepted_extensions.append(extension)

                    # Break out of the loop once we have a match.
                    break

                # If we didn't break from the loop, no extension in our list
                # matched what the client sent. The extension is declined.

        # Serialize extension header.
        if response_header:
            response_header = build_extension_list(response_header)
        else:
            response_header = None

        return response_header, accepted_extensions

    # Not @staticmethod because it calls self.select_subprotocol()
    def process_subprotocol(self, headers, available_subprotocols):
        """
        Handle the Sec-WebSocket-Protocol HTTP request header.

        Return Sec-WebSocket-Protocol HTTP response header, which is the same
        as the selected subprotocol.

        """
        subprotocol = None

        header_values = headers.get_all("Sec-WebSocket-Protocol")

        if header_values and available_subprotocols:

            parsed_header_values = sum(
                [
                    parse_subprotocol_list(header_value)
                    for header_value in header_values
                ],
                [],
            )

            subprotocol = self.select_subprotocol(
                parsed_header_values, available_subprotocols
            )

        return subprotocol

    def select_subprotocol(self, client_subprotocols, server_subprotocols):
        """
        Pick a subprotocol among those offered by the client.

        If several subprotocols are supported by the client and the server,
        the default implementation selects the preferred subprotocols by
        giving equal value to the priorities of the client and the server.

        If no subprotocols are supported by the client and the server, it
        proceeds without a subprotocol.

        This is unlikely to be the most useful implementation in practice, as
        many servers providing a subprotocol will require that the client uses
        that subprotocol. Such rules can be implemented in a subclass.

        This method may be overridden by passing a ``select_subprotocol``
        argument to the :class:`WebSocketServerProtocol` constructor or the
        :func:`serve` function.

        """
        subprotocols = set(client_subprotocols) & set(server_subprotocols)
        if not subprotocols:
            return None
        priority = lambda p: (
            client_subprotocols.index(p) + server_subprotocols.index(p)
        )
        return sorted(subprotocols, key=priority)[0]

    async def handshake(
        self,
        origins=None,
        available_extensions=None,
        available_subprotocols=None,
        extra_headers=None,
    ):
        """
        Perform the server side of the opening handshake.

        If provided, ``origins`` is a list of acceptable HTTP Origin values.
        Include ``None`` if the lack of an origin is acceptable.

        If provided, ``available_extensions`` is a list of supported
        extensions in the order in which they should be used.

        If provided, ``available_subprotocols`` is a list of supported
        subprotocols in order of decreasing preference.

        If provided, ``extra_headers`` sets additional HTTP response headers.
        It can be a :class:`~websockets.http.Headers` instance, a
        :class:`~collections.abc.Mapping`, an iterable of ``(name, value)``
        pairs, or a callable taking the request path and headers in arguments
        and returning one of the above.

        Raise :exc:`~websockets.exceptions.InvalidHandshake` if the handshake
        fails.

        Return the path of the URI of the request.

        """
        path, request_headers = await self.read_http_request()

        # Hook for customizing request handling, for example checking
        # authentication or treating some paths as plain HTTP endpoints.
        if asyncio.iscoroutinefunction(self.process_request):
            early_response = await self.process_request(path, request_headers)
        else:
            early_response = self.process_request(path, request_headers)

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

        if extra_headers is not None:
            if callable(extra_headers):
                extra_headers = extra_headers(path, self.request_headers)
            if isinstance(extra_headers, Headers):
                extra_headers = extra_headers.raw_items()
            elif isinstance(extra_headers, collections.abc.Mapping):
                extra_headers = extra_headers.items()
            for name, value in extra_headers:
                response_headers[name] = value

        response_headers.setdefault("Date", email.utils.formatdate(usegmt=True))
        response_headers.setdefault("Server", USER_AGENT)

        self.write_http_response(http.HTTPStatus.SWITCHING_PROTOCOLS, response_headers)

        self.connection_open()

        return path


class WebSocketServer:
    """
    Wrapper for :class:`~asyncio.Server` that closes connections on exit.

    This class provides the return type of :func:`~websockets.server.serve`.

    It mimics the interface of :class:`~asyncio.AbstractServer`, namely its
    :meth:`~asyncio.AbstractServer.close()` and
    :meth:`~asyncio.AbstractServer.wait_closed()` methods, to close WebSocket
    connections properly on exit, in addition to closing the underlying
    :class:`~asyncio.Server`.

    Instances of this class store a reference to the :class:`~asyncio.Server`
    object returned by :meth:`~asyncio.AbstractEventLoop.create_server` rather
    than inherit from :class:`~asyncio.Server` in part because
    :meth:`~asyncio.AbstractEventLoop.create_server` doesn't support passing a
    custom :class:`~asyncio.Server` class.

    """

    def __init__(self, loop):
        # Store a reference to loop to avoid relying on self.server._loop.
        self.loop = loop

        # Keep track of active connections.
        self.websockets = set()

        # Task responsible for closing the server and terminating connections.
        self.close_task = None

        # Completed when the server is closed and connections are terminated.
        self.closed_waiter = asyncio.Future(loop=loop)

    def wrap(self, server):
        """
        Attach to a given :class:`~asyncio.Server`.

        Since :meth:`~asyncio.AbstractEventLoop.create_server` doesn't support
        injecting a custom ``Server`` class, the easiest solution that doesn't
        rely on private :mod:`asyncio` APIs is to:

        - instantiate a :class:`WebSocketServer`
        - give the protocol factory a reference to that instance
        - call :meth:`~asyncio.AbstractEventLoop.create_server` with the
          factory
        - attach the resulting :class:`~asyncio.Server` with this method

        """
        self.server = server

    def register(self, protocol):
        """
        Register a connection with this server.

        """
        self.websockets.add(protocol)

    def unregister(self, protocol):
        """
        Unregister a connection with this server.

        """
        self.websockets.remove(protocol)

    def is_serving(self):
        """
        Tell whether the server is accepting new connections or shutting down.

        """
        try:
            return self.server.is_serving()  # Python ≥ 3.7
        except AttributeError:  # pragma: no cover
            return self.server.sockets is not None  # Python < 3.7

    def close(self):
        """
        Close the server and terminate connections with close code 1001.

        This method is idempotent.

        """
        if self.close_task is None:
            self.close_task = self.loop.create_task(self._close())

    async def _close(self):
        """
        Implementation of :meth:`close`.

        This calls :meth:`~asyncio.Server.close` on the underlying
        :class:`~asyncio.Server` object to stop accepting new connections and
        then closes open connections with close code 1001.

        """
        # Stop accepting new connections.
        self.server.close()

        # Wait until self.server.close() completes.
        await self.server.wait_closed()

        # Wait until all accepted connections reach connection_made() and call
        # register(). See https://bugs.python.org/issue34852 for details.
        await asyncio.sleep(0)

        # Close open connections. fail_connection() will cancel the transfer
        # data task, which is expected to cause the handler task to terminate.
        for websocket in self.websockets:
            if websocket.state is State.OPEN:
                websocket.fail_connection(1001)

        # asyncio.wait doesn't accept an empty first argument.
        if self.websockets:
            # The connection handler can terminate before or after the
            # connection closes. Wait until both are done to avoid leaking
            # running tasks.
            # TODO: it would be nicer to wait only for the connection handler
            # and let the handler wait for the connection to close.
            await asyncio.wait(
                [websocket.handler_task for websocket in self.websockets]
                + [
                    websocket.close_connection_task
                    for websocket in self.websockets
                    if websocket.state is State.OPEN
                ],
                loop=self.loop,
            )

        # Tell wait_closed() to return.
        self.closed_waiter.set_result(None)

    async def wait_closed(self):
        """
        Wait until the server is closed and all connections are terminated.

        When :meth:`wait_closed()` returns, all TCP connections are closed and
        there are no pending tasks left.

        """
        await asyncio.shield(self.closed_waiter)

    @property
    def sockets(self):
        """
        List of :class:`~socket.socket` objects the server is listening to.

        ``None`` if the server is closed.

        """
        return self.server.sockets


class Serve:
    """
    Create, start, and return a :class:`WebSocketServer`.

    :func:`serve` returns an awaitable. Awaiting it yields an instance of
    :class:`WebSocketServer` which provides
    :meth:`~websockets.server.WebSocketServer.close` and
    :meth:`~websockets.server.WebSocketServer.wait_closed` methods for
    terminating the server and cleaning up its resources.

    :func:`serve` can also be used as an asynchronous context manager. In
    this case, the server is shut down when exiting the context.

    :func:`serve` is a wrapper around the event loop's
    :meth:`~asyncio.AbstractEventLoop.create_server` method. Internally, it
    creates and starts a :class:`~asyncio.Server` object by calling
    :meth:`~asyncio.AbstractEventLoop.create_server`. The
    :class:`WebSocketServer` it returns keeps a reference to this object.

    The ``ws_handler`` argument is the WebSocket handler. It must be a
    coroutine accepting two arguments: a :class:`WebSocketServerProtocol` and
    the request URI.

    The ``host`` and ``port`` arguments, as well as unrecognized keyword
    arguments, are passed along to
    :meth:`~asyncio.AbstractEventLoop.create_server`. For example, you can set
    the ``ssl`` keyword argument to a :class:`~ssl.SSLContext` to enable TLS.

    The ``create_protocol`` parameter allows customizing the asyncio protocol
    that manages the connection. It should be a callable or class accepting
    the same arguments as :class:`WebSocketServerProtocol` and returning a
    :class:`WebSocketServerProtocol` instance. It defaults to
    :class:`WebSocketServerProtocol`.

    The behavior of the ``ping_interval``, ``ping_timeout``, ``close_timeout``,
    ``max_size``, ``max_queue``, ``read_limit``, and ``write_limit`` optional
    arguments is described in the documentation of
    :class:`~websockets.protocol.WebSocketCommonProtocol`.

    :func:`serve` also accepts the following optional arguments:

    * ``compression`` is a shortcut to configure compression extensions;
      by default it enables the "permessage-deflate" extension; set it to
      ``None`` to disable compression
    * ``origins`` defines acceptable Origin HTTP headers — include ``None`` if
      the lack of an origin is acceptable
    * ``extensions`` is a list of supported extensions in order of
      decreasing preference
    * ``subprotocols`` is a list of supported subprotocols in order of
      decreasing preference
    * ``extra_headers`` sets additional HTTP response headers — it can be a
      :class:`~websockets.http.Headers` instance, a
      :class:`~collections.abc.Mapping`, an iterable of ``(name, value)``
      pairs, or a callable taking the request path and headers in arguments
      and returning one of the above
    * ``process_request`` is a callable or a coroutine taking the request path
      and headers in argument, see
      :meth:`~WebSocketServerProtocol.process_request` for details
    * ``select_subprotocol`` is a callable taking the subprotocols offered by
      the client and available on the server in argument, see
      :meth:`~WebSocketServerProtocol.select_subprotocol` for details

    Whenever a client connects, the server accepts the connection, creates a
    :class:`WebSocketServerProtocol`, performs the opening handshake, and
    delegates to the WebSocket handler. Once the handler completes, the server
    performs the closing handshake and closes the connection.

    When a server is closed with :meth:`~WebSocketServer.close`, it closes all
    connections with close code 1001 (going away). WebSocket handlers — which
    are running the coroutine passed in the ``ws_handler`` — will receive a
    :exc:`~websockets.exceptions.ConnectionClosed` exception on their current
    or next interaction with the WebSocket connection.

    Since there's no useful way to propagate exceptions triggered in handlers,
    they're sent to the ``'websockets.server'`` logger instead. Debugging is
    much easier if you configure logging to print them::

        import logging
        logger = logging.getLogger('websockets.server')
        logger.setLevel(logging.ERROR)
        logger.addHandler(logging.StreamHandler())

    """

    def __init__(
        self,
        ws_handler,
        host=None,
        port=None,
        *,
        path=None,
        create_protocol=None,
        ping_interval=20,
        ping_timeout=20,
        close_timeout=None,
        max_size=2 ** 20,
        max_queue=2 ** 5,
        read_limit=2 ** 16,
        write_limit=2 ** 16,
        loop=None,
        legacy_recv=False,
        klass=WebSocketServerProtocol,
        timeout=10,
        compression="deflate",
        origins=None,
        extensions=None,
        subprotocols=None,
        extra_headers=None,
        process_request=None,
        select_subprotocol=None,
        **kwds
    ):
        # Backwards-compatibility: close_timeout used to be called timeout.
        # If both are specified, timeout is ignored.
        if close_timeout is None:
            close_timeout = timeout

        # Backwards-compatibility: create_protocol used to be called klass.
        # If both are specified, klass is ignored.
        if create_protocol is None:
            create_protocol = klass

        if loop is None:
            loop = asyncio.get_event_loop()

        ws_server = WebSocketServer(loop)

        secure = kwds.get("ssl") is not None

        if compression == "deflate":
            if extensions is None:
                extensions = []
            if not any(
                ext_factory.name == ServerPerMessageDeflateFactory.name
                for ext_factory in extensions
            ):
                extensions.append(ServerPerMessageDeflateFactory())
        elif compression is not None:
            raise ValueError("Unsupported compression: {}".format(compression))

        factory = lambda: create_protocol(
            ws_handler,
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
            loop=loop,
            legacy_recv=legacy_recv,
            origins=origins,
            extensions=extensions,
            subprotocols=subprotocols,
            extra_headers=extra_headers,
            process_request=process_request,
            select_subprotocol=select_subprotocol,
        )

        if path is None:
            creating_server = loop.create_server(factory, host, port, **kwds)
        else:
            creating_server = loop.create_unix_server(factory, path, **kwds)

        # This is a coroutine object.
        self._creating_server = creating_server
        self.ws_server = ws_server

    @asyncio.coroutine
    def __iter__(self):
        return self.__await_impl__()

    async def __aenter__(self):
        return await self

    async def __aexit__(self, exc_type, exc_value, traceback):
        self.ws_server.close()
        await self.ws_server.wait_closed()

    async def __await_impl__(self):
        server = await self._creating_server
        self.ws_server.wrap(server)
        return self.ws_server

    def __await__(self):
        # __await__() must return a type that I don't know how to obtain except
        # by calling __await__() on the return value of an async function.
        # I'm not finding a better way to take advantage of PEP 492.
        return self.__await_impl__().__await__()


def unix_serve(ws_handler, path, **kwargs):
    """
    Similar to :func:`serve()`, but for listening on Unix sockets.

    This function calls the event loop's
    :meth:`~asyncio.AbstractEventLoop.create_unix_server` method.

    It is only available on Unix.

    It's useful for deploying a server behind a reverse proxy such as nginx.

    """
    return serve(ws_handler, path=path, **kwargs)


# We can't define __await__ on Python < 3.5.1 because asyncio.ensure_future
# didn't accept arbitrary awaitables until Python 3.5.1. We don't define
# __aenter__ and __aexit__ either on Python < 3.5.1 to keep things simple.
if sys.version_info[:3] < (3, 5, 1):  # pragma: no cover

    del Serve.__aenter__
    del Serve.__aexit__
    del Serve.__await__

    async def serve(*args, **kwds):
        return Serve(*args, **kwds).__iter__()

    serve.__doc__ = Serve.__doc__

else:

    serve = Serve
