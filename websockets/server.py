
"""
The :mod:`websockets.server` module defines a simple WebSocket server API.

"""

import asyncio
import collections.abc
import email.message
import http
import logging

from .compatibility import asyncio_ensure_future
from .exceptions import InvalidHandshake, InvalidMessage, InvalidOrigin
from .extensions import PerMessageDeflate
from .handshake import build_response, check_request
from .http import USER_AGENT, read_request
from .protocol import CONNECTING, OPEN, WebSocketCommonProtocol


__all__ = ['serve', 'WebSocketServerProtocol']

logger = logging.getLogger(__name__)

try:
    SWITCHING_PROTOCOLS = http.HTTPStatus.SWITCHING_PROTOCOLS
except AttributeError:                                      # pragma: no cover
    class SWITCHING_PROTOCOLS:
        value = 101
        phrase = 'Switching protocols'


class WebSocketServerProtocol(WebSocketCommonProtocol):
    """
    Complete WebSocket server implementation as an :class:`asyncio.Protocol`.

    This class inherits most of its methods from
    :class:`~websockets.protocol.WebSocketCommonProtocol`.

    For the sake of simplicity, it doesn't rely on a full HTTP implementation.
    Its support for HTTP responses is very limited.

    """
    state = CONNECTING

    def __init__(self, ws_handler, ws_server, *,
                 origins=None, extensions=None, subprotocols=None,
                 extra_headers=None, **kwds):
        self.ws_handler = ws_handler
        self.ws_server = ws_server
        self.origins = origins
        self.available_extensions = extensions
        self.available_subprotocols = subprotocols
        self.extra_headers = extra_headers
        super().__init__(**kwds)

    def connection_made(self, transport):
        super().connection_made(transport)
        # Register the connection with the server when creating the handler
        # task. (Registering at the beginning of the handler coroutine would
        # create a race condition between the creation of the task, which
        # schedules its execution, and the moment the handler starts running.)
        self.ws_server.register(self)
        self.handler_task = asyncio_ensure_future(
            self.handler(), loop=self.loop)

    @asyncio.coroutine
    def handler(self):
        # Since this method doesn't have a caller able to handle exceptions,
        # it attemps to log relevant ones and close the connection properly.
        try:

            try:
                path = yield from self.handshake(
                    origins=self.origins,
                    available_extensions=self.available_extensions,
                    available_subprotocols=self.available_subprotocols,
                    extra_headers=self.extra_headers,
                )
            except ConnectionError as exc:
                logger.debug(
                    "Connection error in opening handshake", exc_info=True)
                raise
            except Exception as exc:
                if self._is_server_shutting_down(exc):
                    response = ('HTTP/1.1 503 Service Unavailable\r\n\r\n'
                                'Server is shutting down.')
                elif isinstance(exc, InvalidOrigin):
                    response = 'HTTP/1.1 403 Forbidden\r\n\r\n' + str(exc)
                elif isinstance(exc, InvalidHandshake):
                    response = 'HTTP/1.1 400 Bad Request\r\n\r\n' + str(exc)
                else:
                    logger.warning("Error in opening handshake", exc_info=True)
                    response = ('HTTP/1.1 500 Internal Server Error\r\n\r\n'
                                'See server log for more information.')
                self.writer.write(response.encode())
                raise

            # Subclasses can customize get_response_status() or handshake() to
            # reject the handshake, typically after checking authentication.
            if path is None:
                return

            try:
                yield from self.ws_handler(self, path)
            except Exception as exc:
                if self._is_server_shutting_down(exc):
                    yield from self.fail_connection(1001)
                else:
                    logger.error("Error in connection handler", exc_info=True)
                    yield from self.fail_connection(1011)
                raise

            try:
                yield from self.close()
            except ConnectionError as exc:
                logger.debug(
                    "Connection error in closing handshake", exc_info=True)
                raise
            except Exception as exc:
                if not self._is_server_shutting_down(exc):
                    logger.warning("Error in closing handshake", exc_info=True)
                raise

        except Exception:
            # Last-ditch attempt to avoid leaking connections on errors.
            try:
                self.writer.close()
            except Exception:                               # pragma: no cover
                pass

        finally:
            # Unregister the connection with the server when the handler task
            # terminates. Registration is tied to the lifecycle of the handler
            # task because the server waits for tasks attached to registered
            # connections before terminating.
            self.ws_server.unregister(self)

    def _is_server_shutting_down(self, exc):
        """
        Decide whether an exception means that the server is shutting down.

        """
        return (
            isinstance(exc, asyncio.CancelledError) and
            self.ws_server.closing
        )

    @asyncio.coroutine
    def read_http_request(self):
        """
        Read status line and headers from the HTTP request.

        Raise :exc:`~websockets.exceptions.InvalidMessage` if the HTTP message
        is malformed or isn't a HTTP/1.1 GET request.

        """
        try:
            path, headers = yield from read_request(self.reader)
        except ValueError as exc:
            raise InvalidMessage("Malformed HTTP message") from exc

        self.path = path
        self.request_headers = headers
        self.raw_request_headers = list(headers.raw_items())

        return path, headers

    @asyncio.coroutine
    def write_http_response(self, status, headers):
        """
        Write status line and headers to the HTTP response.

        """
        self.response_headers = email.message.Message()
        for name, value in headers:
            self.response_headers[name] = value
        self.raw_response_headers = headers

        # Since the status line and headers only contain ASCII characters,
        # we can keep this simple.
        response = [
            'HTTP/1.1 {value} {phrase}'.format(
                value=status.value, phrase=status.phrase)]
        response.extend('{}: {}'.format(k, v) for k, v in headers)
        response.append('\r\n')
        response = '\r\n'.join(response).encode()

        self.writer.write(response)

    def process_origin(self, get_header, origins=None):
        """
        Handle the Origin HTTP request header.

        Raise :exc:`~websockets.exceptions.InvalidOrigin` if the origin isn't
        acceptable.

        """
        if origins is not None:
            origin = get_header('Origin')
            if origin not in origins:
                raise InvalidOrigin("Origin not allowed: {}".format(origin))
            return origin

    def process_extensions(self, get_header, available_extensions=None):
        """
        Handle the Sec-WebSocket-Extensions HTTP request header.

        """
        # TODO this doesn't allow configuring available extensions.
        extensions = get_header('Sec-WebSocket-Extensions')
        if extensions:
            extensions = [
                extension.strip()
                for extension in extensions.split(',')
            ]
            for extension in extensions:
                extension, params = extension.split(';', 1)
                if extension == 'permessage-deflate':
                    return [PerMessageDeflate(params)]
        return []

    def process_subprotocol(self, get_header, available_subprotocols=None):
        """
        Handle the Sec-WebSocket-Protocol HTTP request header.

        """
        if available_subprotocols is not None:
            subprotocols = get_header('Sec-WebSocket-Protocol')
            if subprotocols:
                subprotocols = [
                    subprotocol.strip()
                    for subprotocol in subprotocols.split(',')
                ]
                return self.select_subprotocol(
                    subprotocols,
                    available_subprotocols,
                )

    @staticmethod
    def select_subprotocol(client_subprotocols, server_subprotocols):
        """
        Pick a subprotocol among those offered by the client.

        """
        subprotocols = set(client_subprotocols) & set(server_subprotocols)
        if not subprotocols:
            return None
        priority = lambda p: (
            client_subprotocols.index(p) + server_subprotocols.index(p))
        return sorted(subprotocols, key=priority)[0]

    @asyncio.coroutine
    def get_response_status(self, set_header):
        """
        Return a :class:`~http.HTTPStatus` for the HTTP response.

        (:class:`~http.HTTPStatus` was added in Python 3.5. On earlier
        versions, a compatible object must be returned. Check the definition
        of ``SWITCHING_PROTOCOLS`` for an example.)

        This method may be overridden to check the request headers and set a
        different status, for example to authenticate the request and return
        ``HTTPStatus.UNAUTHORIZED`` or ``HTTPStatus.FORBIDDEN``.

        It is declared as a coroutine because such authentication checks are
        likely to require network requests.

        The connection is closed immediately after sending the response when
        the status code is not ``HTTPStatus.SWITCHING_PROTOCOLS``.

        Call ``set_header(key, value)`` to set additional response headers.

        """
        return SWITCHING_PROTOCOLS

    @asyncio.coroutine
    def handshake(self, origins=None,
                  available_extensions=None, available_subprotocols=None,
                  extra_headers=None):
        """
        Perform the server side of the opening handshake.

        If provided, ``origins`` is a list of acceptable HTTP Origin values.
        Include ``''`` if the lack of an origin is acceptable.

        If provided, ``available_extensions`` is a list of supported
        extensions in the order in which they should be used.

        If provided, ``available_subprotocols`` is a list of supported
        subprotocols in order of decreasing preference.

        If provided, ``extra_headers`` sets additional HTTP response headers.
        It can be a mapping or an iterable of (name, value) pairs. It can also
        be a callable taking the request path and headers in arguments.

        Raise :exc:`~websockets.exceptions.InvalidHandshake` or a subclass if
        the handshake fails.

        Return the URI of the request.

        """
        path, headers = yield from self.read_http_request()
        get_header = lambda k: headers.get(k, '')

        key = check_request(get_header)

        self.origin = self.process_origin(get_header, origins)

        self.extensions = self.process_extensions(
            get_header, available_extensions)

        self.subprotocol = self.process_subprotocol(
            get_header, available_subprotocols)

        headers = []
        set_header = lambda k, v: headers.append((k, v))

        set_header('Server', USER_AGENT)

        status = yield from self.get_response_status(set_header)

        # Abort the connection if the status code isn't 101.
        if status.value != SWITCHING_PROTOCOLS.value:
            yield from self.write_http_response(status, headers)
            self.opening_handshake.set_result(False)
            yield from self.close_connection(force=True)
            return

        # Status code is 101, establish the connection.
        if self.extensions:
            set_header('Sec-WebSocket-Extensions', ', '.join(
                extension.response() for extension in self.extensions))
        if self.subprotocol:
            set_header('Sec-WebSocket-Protocol', self.subprotocol)
        if extra_headers is not None:
            if callable(extra_headers):
                extra_headers = extra_headers(path, self.raw_request_headers)
            if isinstance(extra_headers, collections.abc.Mapping):
                extra_headers = extra_headers.items()
            for name, value in extra_headers:
                set_header(name, value)
        build_response(set_header, key)

        yield from self.write_http_response(status, headers)

        assert self.state == CONNECTING
        self.state = OPEN
        self.opening_handshake.set_result(True)

        return path


class WebSocketServer(asyncio.AbstractServer):
    """
    Wrapper for :class:`~asyncio.Server` that triggers the closing handshake.

    """
    def __init__(self, loop):
        # Store a reference to loop to avoid relying on self.server._loop.
        self.loop = loop

        self.closing = False
        self.websockets = set()

    def wrap(self, server):
        """
        Attach to a given :class:`~asyncio.Server`.

        Since :meth:`~asyncio.BaseEventLoop.create_server` doesn't support
        injecting a custom ``Server`` class, a simple solution that doesn't
        rely on private APIs is to:

        - instantiate a :class:`WebSocketServer`
        - give the protocol factory a reference to that instance
        - call :meth:`~asyncio.BaseEventLoop.create_server` with the factory
        - attach the resulting :class:`~asyncio.Server` with this method

        """
        self.server = server

    def register(self, protocol):
        self.websockets.add(protocol)

    def unregister(self, protocol):
        self.websockets.remove(protocol)

    def close(self):
        """
        Stop accepting new connections and close open connections.

        """
        # Make a note that the server is shutting down. Websocket connections
        # check this attribute to decide to send a "going away" close code.
        self.closing = True

        # Stop accepting new connections.
        self.server.close()

        # Close open connections. For each connection, two tasks are running:
        # 1. self.worker_task shuffles messages between the network and queues
        # 2. self.handler_task runs the opening handshake, the handler provided
        #    by the user and the closing handshake
        # In the general case, cancelling the handler task will cause the
        # handler provided by the user to exit with a CancelledError, which
        # will then cause the worker task to terminate.
        for websocket in self.websockets:
            websocket.handler_task.cancel()

    @asyncio.coroutine
    def wait_closed(self):
        """
        Wait until all connections are closed.

        This method must be called after :meth:`close()`.

        """
        # asyncio.wait doesn't accept an empty first argument.
        if self.websockets:
            # The handler or the worker task can terminate first, depending
            # on how the client behaves and the server is implemented.
            yield from asyncio.wait(
                [websocket.handler_task for websocket in self.websockets] +
                [websocket.worker_task for websocket in self.websockets],
                loop=self.loop)
        yield from self.server.wait_closed()


@asyncio.coroutine
def serve(ws_handler, host=None, port=None, *,
          klass=WebSocketServerProtocol,
          timeout=10, max_size=2 ** 20, max_queue=2 ** 5,
          read_limit=2 ** 16, write_limit=2 ** 16,
          loop=None, legacy_recv=False,
          origins=None, extensions=None, subprotocols=None,
          extra_headers=None, **kwds):
    """
    This coroutine creates a WebSocket server.

    It yields a :class:`~asyncio.Server` which provides:

    * a :meth:`~asyncio.Server.close` method that closes open connections with
      status code 1001 and stops accepting new connections
    * a :meth:`~asyncio.Server.wait_closed` coroutine that waits until closing
      handshakes complete and connections are closed.

    ``ws_handler`` is the WebSocket handler. It must be a coroutine accepting
    two arguments: a :class:`WebSocketServerProtocol` and the request URI.

    :func:`serve` is a wrapper around the event loop's
    :meth:`~asyncio.BaseEventLoop.create_server` method. ``host``, ``port`` as
    well as unknown keyword arguments are passed to
    :meth:`~asyncio.BaseEventLoop.create_server`.

    For example, you can set the ``ssl`` keyword argument to a
    :class:`~ssl.SSLContext` to enable TLS.

    The behavior of the ``timeout``, ``max_size``, and ``max_queue``,
    ``read_limit``, and ``write_limit`` optional arguments is described in the
    documentation of :class:`~websockets.protocol.WebSocketCommonProtocol`.

    :func:`serve` also accepts the following optional arguments:

    * ``origins`` defines acceptable Origin HTTP headers — include
      ``''`` if the lack of an origin is acceptable
    * ``extensions`` is a list of supported extensions in order of decreasing
      preference
    * ``subprotocols`` is a list of supported subprotocols in order of
      decreasing preference
    * ``extra_headers`` sets additional HTTP response headers — it can be a
      mapping, an iterable of (name, value) pairs, or a callable taking the
      request path and headers in arguments.

    Whenever a client connects, the server accepts the connection, creates a
    :class:`WebSocketServerProtocol`, performs the opening handshake, and
    delegates to the WebSocket handler. Once the handler completes, the server
    performs the closing handshake and closes the connection.

    Since there's no useful way to propagate exceptions triggered in handlers,
    they're sent to the ``'websockets.server'`` logger instead. Debugging is
    much easier if you configure logging to print them::

        import logging
        logger = logging.getLogger('websockets.server')
        logger.setLevel(logging.ERROR)
        logger.addHandler(logging.StreamHandler())

    On Python 3.5, :func:`serve` can be used as a asynchronous context
    manager. In that case, the server is shut down when exiting the context.

    """
    if loop is None:
        loop = asyncio.get_event_loop()

    ws_server = WebSocketServer(loop)

    secure = kwds.get('ssl') is not None
    factory = lambda: klass(
        ws_handler, ws_server,
        host=host, port=port, secure=secure,
        timeout=timeout, max_size=max_size, max_queue=max_queue,
        read_limit=read_limit, write_limit=write_limit,
        loop=loop, legacy_recv=legacy_recv,
        origins=origins, extensions=extensions, subprotocols=subprotocols,
        extra_headers=extra_headers,
    )
    server = yield from loop.create_server(factory, host, port, **kwds)

    ws_server.wrap(server)

    return ws_server


try:
    from .py35.server import Serve
except (SyntaxError, ImportError):                          # pragma: no cover
    pass
else:
    Serve.__wrapped__ = serve
    # Copy over docstring to support building documentation on Python 3.5.
    Serve.__doc__ = serve.__doc__
    serve = Serve
