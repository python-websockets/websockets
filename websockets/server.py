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
    Complete WebSocket server implementation as a Tulip protocol.

    This class inherits most of its methods from
    :class:`~websockets.protocol.WebSocketCommonProtocol`.

    For the sake of simplicity, this protocol doesn't inherit a proper HTTP
    implementation, and it doesn't send appropriate HTTP responses when
    something goes wrong.
    """

    state = 'CONNECTING'

    def __init__(self, ws_handler=None, **kwargs):
        self.ws_handler = ws_handler
        super().__init__(**kwargs)

    def connection_made(self, transport):
        super().connection_made(transport)
        asyncio.async(self.handler())

    @asyncio.coroutine
    def handler(self):
        try:
            uri = yield from self.handshake()
        except Exception as exc:
            logger.info("Exception in opening handshake: {}".format(exc))
            self.transport.close()
            return

        try:
            yield from self.ws_handler(self, uri)
        except Exception:
            logger.info("Exception in connection handler", exc_info=True)
            yield from self.fail_connection(1011)
            return

        try:
            yield from self.close()
        except Exception as exc:
            logger.info("Exception in closing handshake: {}".format(exc))
            self.transport.close()
            return

    @asyncio.coroutine
    def handshake(self):
        """
        Perform the server side of the opening handshake.

        Return the URI of the request.
        """
        # Read handshake request.
        try:
            uri, headers = yield from read_request(self.stream)
        except Exception as exc:
            raise InvalidHandshake("Malformed HTTP message") from exc
        get_header = lambda k: headers.get(k, '')
        key = check_request(get_header)

        # Send handshake response. Since the headers only contain ASCII
        # characters, we can keep this simple.
        response = ['HTTP/1.1 101 Switching Protocols']
        set_header = lambda k, v: response.append('{}: {}'.format(k, v))
        set_header('Server', USER_AGENT)
        build_response(set_header, key)
        response.append('\r\n')
        response = '\r\n'.join(response).encode()
        self.transport.write(response)

        self.state = 'OPEN'
        self.opening_handshake.set_result(True)

        return uri


@asyncio.coroutine
def serve(ws_handler, host=None, port=None, *,
          klass=WebSocketServerProtocol, **kwds):
    """
    This coroutine creates a WebSocket server.

    It's a thin wrapper around the event loop's ``create_server`` method.
    ``host``, ``port`` as well as extra keyword arguments are passed to
    ``create_server``.

    It returns a ``Server`` object with a ``close`` method to stop the server.

    `ws_handler` is the WebSocket handler. It must be a coroutine accepting
    two arguments: a :class:`~websockets.server.WebSocketServerProtocol` and
    the request URI. The `host` and `port` arguments and other keyword
    arguments are passed to ``create_server``.

    Whenever a client connects, the server accepts the connection, creates a
    :class:`~websockets.server.WebSocketServerProtocol`, performs the opening
    handshake, and delegates to the WebSocket handler. Once the handler
    completes, the server performs the closing handshake and closes the
    connection.
    """
    return (yield from asyncio.get_event_loop().create_server(
            lambda: klass(ws_handler), host, port, **kwds))
