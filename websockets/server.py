"""
The :mod:`websockets.server` module defines a simple WebSocket server API.

"""

import asyncio
import collections.abc
import email.message
import logging

from .compatibility import asyncio_ensure_future
from .exceptions import InvalidHandshake, InvalidOrigin
from .handshake import build_response, check_request
from .http import USER_AGENT, read_request
from .protocol import CONNECTING, OPEN, WebSocketCommonProtocol


__all__ = ['serve', 'WebSocketServerProtocol']

logger = logging.getLogger(__name__)


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
                 origins=None, subprotocols=None, extra_headers=None, **kwds):
        self.ws_handler = ws_handler
        self.ws_server = ws_server
        self.origins = origins
        self.subprotocols = subprotocols
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
                    origins=self.origins, subprotocols=self.subprotocols,
                    extra_headers=self.extra_headers)
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
            except Exception as exc:
                if self._is_server_shutting_down(exc):
                    pass
                else:
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
    def handshake(self, origins=None, subprotocols=None, extra_headers=None):
        """
        Perform the server side of the opening handshake.

        If provided, ``origins`` is a list of acceptable HTTP Origin values.
        Include ``''`` if the lack of an origin is acceptable.

        If provided, ``subprotocols`` is a list of supported subprotocols in
        order of decreasing preference.

        If provided, ``extra_headers`` sets additional HTTP response headers.
        It can be a mapping or an iterable of (name, value) pairs. It can also
        be a callable taking the request path and headers in arguments.

        Return the URI of the request.

        """
        # Read handshake request.
        try:
            path, headers = yield from read_request(self.reader)
        except ValueError as exc:
            raise InvalidHandshake("Malformed HTTP message") from exc

        self.request_headers = headers
        self.raw_request_headers = list(headers.raw_items())

        get_header = lambda k: headers.get(k, '')
        key = check_request(get_header)

        if origins is not None:
            origin = get_header('Origin')
            if not set(origin.split() or ['']) <= set(origins):
                raise InvalidOrigin("Origin not allowed: {}".format(origin))

        if subprotocols is not None:
            protocol = get_header('Sec-WebSocket-Protocol')
            if protocol:
                client_subprotocols = [p.strip() for p in protocol.split(',')]
                self.subprotocol = self.select_subprotocol(
                    client_subprotocols, subprotocols)

        headers = []
        set_header = lambda k, v: headers.append((k, v))
        set_header('Server', USER_AGENT)
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

        self.response_headers = email.message.Message()
        for name, value in headers:
            self.response_headers[name] = value
        self.raw_response_headers = headers

        # Send handshake response. Since the status line and headers only
        # contain ASCII characters, we can keep this simple.
        response = ['HTTP/1.1 101 Switching Protocols']
        response.extend('{}: {}'.format(k, v) for k, v in headers)
        response.append('\r\n')
        response = '\r\n'.join(response).encode()
        self.writer.write(response)

        assert self.state == CONNECTING
        self.state = OPEN
        self.opening_handshake.set_result(True)

        return path

    @staticmethod
    def select_subprotocol(client_protos, server_protos):
        """
        Pick a subprotocol among those offered by the client.

        """
        common_protos = set(client_protos) & set(server_protos)
        if not common_protos:
            return None
        priority = lambda p: client_protos.index(p) + server_protos.index(p)
        return sorted(common_protos, key=priority)[0]


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
          loop=None, legacy_recv=False,
          origins=None, subprotocols=None, extra_headers=None,
          **kwds):
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
    well as extra keyword arguments are passed to
    :meth:`~asyncio.BaseEventLoop.create_server`.

    For example, you can set the ``ssl`` keyword argument to a
    :class:`~ssl.SSLContext` to enable TLS.

    The behavior of the ``timeout``, ``max_size``, and ``max_queue`` optional
    arguments is described the documentation of
    :class:`~websockets.protocol.WebSocketCommonProtocol`.

    :func:`serve` also accepts the following optional arguments:

    * ``origins`` defines acceptable Origin HTTP headers — include
      ``''`` if the lack of an origin is acceptable
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

    """
    if loop is None:
        loop = asyncio.get_event_loop()

    ws_server = WebSocketServer(loop)

    secure = kwds.get('ssl') is not None
    factory = lambda: klass(
        ws_handler, ws_server,
        host=host, port=port, secure=secure,
        timeout=timeout, max_size=max_size, max_queue=max_queue,
        loop=loop, legacy_recv=legacy_recv,
        origins=origins, subprotocols=subprotocols,
        extra_headers=extra_headers,
    )
    server = yield from loop.create_server(factory, host, port, **kwds)

    ws_server.wrap(server)

    return ws_server
