"""
The :mod:`websockets.server` module defines a simple WebSocket server API.
"""

__all__ = ['serve', 'WebSocketServerProtocol']

import collections.abc
import logging

import asyncio

from .exceptions import InvalidHandshake
from .handshake import check_request, build_response
from .http import read_request, USER_AGENT
from .protocol import WebSocketCommonProtocol


logger = logging.getLogger(__name__)


class WebSocketServerProtocol(WebSocketCommonProtocol):
    """
    Complete WebSocket server implementation as an :mod:`asyncio` protocol.

    This class inherits most of its methods from
    :class:`~websockets.protocol.WebSocketCommonProtocol`.

    For the sake of simplicity, this protocol doesn't inherit a proper HTTP
    implementation. Its support for HTTP responses is very limited.
    """

    state = 'CONNECTING'

    def __init__(self, ws_handler, *,
                 origins=None, subprotocols=None, extra_headers=None, **kwds):
        self.ws_handler = ws_handler
        self.origins = origins
        self.subprotocols = subprotocols
        self.extra_headers = extra_headers
        super().__init__(**kwds)

    def connection_made(self, transport):
        super().connection_made(transport)
        asyncio.async(self.handler(), loop=self._loop)

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
                logger.info("Exception in opening handshake: {}".format(exc))
                if isinstance(exc, InvalidHandshake):
                    response = 'HTTP/1.1 400 Bad Request\r\n\r\n' + str(exc)
                else:
                    response = ('HTTP/1.1 500 Internal Server Error\r\n\r\n'
                                'See server log for more information.')
                self.writer.write(response.encode())
                raise

            try:
                yield from self.ws_handler(self, path)
            except Exception:
                logger.error("Exception in connection handler", exc_info=True)
                yield from self.fail_connection(1011)
                raise

            try:
                yield from self.close()
            except Exception as exc:
                logger.info("Exception in closing handshake: {}".format(exc))
                raise

        except Exception:
            # Last-ditch attempt to avoid leaking connections on errors.
            try:
                self.writer.close()
            except Exception:                               # pragma: no cover
                pass

    @asyncio.coroutine
    def handshake(self, origins=None, subprotocols=None, extra_headers=None):
        """
        Perform the server side of the opening handshake.

        If provided, ``origins`` is a list of acceptable HTTP Origin values.
        Include ``''`` if the lack of an origin is acceptable.

        If provided, ``subprotocols`` is a list of supported subprotocols in
        order of decreasing preference.

        If provided, ``extra_headers`` sets additional HTTP response headers.
        It must be a mapping or an iterable of (name, value) pairs.

        Return the URI of the request.
        """
        # Read handshake request.
        try:
            path, headers = yield from read_request(self.reader)
        except Exception as exc:
            raise InvalidHandshake("Malformed HTTP message") from exc

        self.raw_request_headers = list(headers.raw_items())
        get_header = lambda k: headers.get(k, '')
        key = check_request(get_header)

        if origins is not None:
            origin = get_header('Origin')
            if not set(origin.split() or ['']) <= set(origins):
                raise InvalidHandshake("Bad origin: {}".format(origin))

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
            if isinstance(extra_headers, collections.abc.Mapping):
                extra_headers = extra_headers.items()
            for name, value in extra_headers:
                set_header(name, value)
        build_response(set_header, key)
        self.raw_response_headers = headers

        # Send handshake response. Since the status line and headers only
        # contain ASCII characters, we can keep this simple.
        response = ['HTTP/1.1 101 Switching Protocols']
        response.extend('{}: {}'.format(k, v) for k, v in headers)
        response.append('\r\n')
        response = '\r\n'.join(response).encode()
        self.writer.write(response)

        self.state = 'OPEN'
        self.opening_handshake.set_result(True)

        return path

    def select_subprotocol(self, client_protos, server_protos):
        """
        Pick a subprotocol among those offered by the client.
        """
        common_protos = set(client_protos) & set(server_protos)
        if not common_protos:
            return None
        priority = lambda p: client_protos.index(p) + server_protos.index(p)
        return sorted(common_protos, key=priority)[0]


@asyncio.coroutine
def serve(ws_handler, host=None, port=None, *,
          loop=None, klass=WebSocketServerProtocol,
          origins=None, subprotocols=None, extra_headers=None,
          **kwds):
    """
    This coroutine creates a WebSocket server.

    It's a thin wrapper around the event loop's
    :meth:`~asyncio.BaseEventLoop.create_server` method. `host`, `port` as
    well as extra keyword arguments are passed to
    :meth:`~asyncio.BaseEventLoop.create_server`.

    ``ws_handler`` is the WebSocket handler. It must be a coroutine accepting
    two arguments: a :class:`~websockets.server.WebSocketServerProtocol` and
    the request URI.

    This coroutine accepts several optional arguments:

    * ``origins`` defines acceptable Origin HTTP headers — include
      ``''`` if the lack of an origin is acceptable
    * ``subprotocols`` is a list of supported subprotocols in order of
        decreasing preference
    * ``extra_headers`` sets additional HTTP response headers – it can be a
      mapping or an iterable of (name, value) pairs

    `serve` yields a `Server` object with a `close` method to stop the server.

    Whenever a client connects, the server accepts the connection, creates a
    :class:`~websockets.server.WebSocketServerProtocol`, performs the opening
    handshake, and delegates to the WebSocket handler. Once the handler
    completes, the server performs the closing handshake and closes the
    connection.

    Since there's no useful way to propagate exceptions triggered in handlers,
    they're sent to the `websockets.server` logger instead. Debugging is much
    easier if you configure logging to print them::

        import logging
        logger = logging.getLogger('websockets.server')
        logger.setLevel(logging.DEBUG)
        logger.addHandler(logging.StreamHandler())
    """
    if loop is None:
        loop = asyncio.get_event_loop()

    secure = kwds.get('ssl') is not None
    factory = lambda: klass(
            ws_handler, host=host, port=port, secure=secure,
            origins=origins, subprotocols=subprotocols,
            extra_headers=extra_headers, loop=loop)
    return (yield from loop.create_server(factory, host, port, **kwds))
