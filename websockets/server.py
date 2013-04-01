"""
The :mod:`websockets.server` module contains a sample WebSocket server
implementation.
"""

__all__ = ['serve']

import tulip

from .framing import *
from .handshake import *
from .http import *


def serve(ws_handler, host=None, port=None, *, protocols=(), extensions=(), **kwargs):
    """
    This task starts a WebSocket server.

    `ws_handler` is the WebSocket handler. It must be a coroutine accepting
    two arguments: a :class:`~websockets.framing.WebSocketProtocol` and the
    request URI. The `host` and `port` arguments and other keyword arguments
    are passed to the event loop's ``start_serving`` method.

    Whenever a client connects, the server accepts the connection, creates a
    :class:`~websockets.framing.WebSocketProtocol`, performs the opening
    handshake, and delegates to the WebSocket handler. Once the handler
    completes, the server performs the closing handshake and closes the
    connection.
    """
    assert not protocols, "protocols aren't supported"
    assert not extensions, "extensions aren't supported"

    yield from tulip.get_event_loop().start_serving(
            lambda: WebSocketServerProtocol(ws_handler), host, port, **kwargs)


# Workaround for http://code.google.com/p/tulip/issues/detail?id=30
__serve_doc__ = serve.__doc__
serve = tulip.task(serve)
serve.__doc__ = __serve_doc__


class WebSocketServerProtocol(WebSocketProtocol):
    """
    Complete WebSocket server implementation as a Tulip protocol.

    TODO: for the sake of simplicity, this protocol doesn't inherit a proper
    HTTP implementation, and it doesn't send appropriate HTTP responses when
    something goes wrong.
    """

    def __init__(self, ws_handler, *args, **kwargs):
        self.ws_handler = ws_handler
        super().__init__(*args, **kwargs)

    def connection_made(self, transport):
        super().connection_made(transport)
        self.handle_request()

    @tulip.task
    def handle_request(self):
        uri = yield from self.handshake()
        yield from self.ws_handler(self, uri)
        yield from self.close()

    @tulip.coroutine
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

        return uri
