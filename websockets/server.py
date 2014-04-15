"""
The :mod:`websockets.server` module defines a simple WebSocket server API.
"""

__all__ = ['serve', 'WebSocketServerProtocol']

import logging

import asyncio

from .exceptions import InvalidHandshake
from .handshake import check_request, build_response
from .http import read_request, USER_AGENT
from .protocol import WebSocketCommonProtocol


logger = logging.getLogger(__name__)


class WebSocketServerProtocol(WebSocketCommonProtocol):
    """
    Complete WebSocket server implementation as an asyncio protocol.

    This class inherits most of its methods from
    :class:`~websockets.protocol.WebSocketCommonProtocol`.

    For the sake of simplicity, this protocol doesn't inherit a proper HTTP
    implementation. Its support for HTTP responses is very limited.
    """

    state = 'CONNECTING'

    def __init__(self, ws_handler=None, *, origins=None, **kwargs):
        self.ws_handler = ws_handler
        self.origins = origins
        super().__init__(**kwargs)

    def connection_made(self, transport):
        super().connection_made(transport)
        asyncio.async(self.handler())

    @asyncio.coroutine
    def handler(self):
        try:
            path = yield from self.handshake(origins=self.origins)
        except Exception as exc:
            logger.info("Exception in opening handshake: {}".format(exc))
            if isinstance(exc, InvalidHandshake):
                response = 'HTTP/1.1 400 Bad Request\r\n\r\n' + str(exc)
            else:
                response = ('HTTP/1.1 500 Internal Server Error\r\n\r\n'
                            'See server log for more information.')
            self.writer.write(response.encode())
            self.writer.close()
            return

        try:
            yield from self.ws_handler(self, path)
        except Exception:
            logger.info("Exception in connection handler", exc_info=True)
            yield from self.fail_connection(1011)
            return

        try:
            yield from self.close()
        except Exception as exc:
            logger.info("Exception in closing handshake: {}".format(exc))
            self.writer.close()
            return

    @asyncio.coroutine
    def handshake(self, origins=None):
        """
        Perform the server side of the opening handshake.

        If provided, ``origins`` is a list of acceptable HTTP Origin values.
        Include ``''`` in the list if the lack of an origin is acceptable.

        Return the URI of the request.
        """
        # Read handshake request.
        try:
            path, headers = yield from read_request(self.reader)
        except Exception as exc:
            raise InvalidHandshake("Malformed HTTP message") from exc

        get_header = lambda k: headers.get(k, '')
        key = check_request(get_header)

        # Check origin in request.
        if origins is not None:
            origin = get_header('Origin')
            if not set(origin.split() or ('',))<= set(origins):
                raise InvalidHandshake("Bad origin: {}".format(origin))

        # Send handshake response. Since the headers only contain ASCII
        # characters, we can keep this simple.
        response = ['HTTP/1.1 101 Switching Protocols']
        set_header = lambda k, v: response.append('{}: {}'.format(k, v))
        set_header('Server', USER_AGENT)
        build_response(set_header, key)
        response.append('\r\n')
        response = '\r\n'.join(response).encode()
        self.writer.write(response)

        self.state = 'OPEN'
        self.opening_handshake.set_result(True)

        return path


@asyncio.coroutine
def serve(ws_handler, host=None, port=None, *,
          klass=WebSocketServerProtocol, origins=None, **kwds):
    """
    This coroutine creates a WebSocket server.

    It's a thin wrapper around the event loop's `create_server` method.
    `host`, `port` as well as extra keyword arguments are passed to
    `create_server`.

    `ws_handler` is the WebSocket handler. It must be a coroutine accepting
    two arguments: a :class:`~websockets.server.WebSocketServerProtocol` and
    the request URI. `origin` is a list of acceptable Origin HTTP headers.

    It returns a `Server` object with a `close` method to stop the server.

    Whenever a client connects, the server accepts the connection, creates a
    :class:`~websockets.server.WebSocketServerProtocol`, performs the opening
    handshake, and delegates to the WebSocket handler. Once the handler
    completes, the server performs the closing handshake and closes the
    connection.
    """
    return (yield from asyncio.get_event_loop().create_server(
            lambda: klass(ws_handler, origins=origins), host, port, **kwds))
