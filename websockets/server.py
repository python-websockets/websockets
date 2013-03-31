"""
Sample WebSocket server implementation.

It demonstrates how to tie together the handshake and framing APIs.
"""

__all__ = ['serve', 'WebSocketServerProtocol']

import re

import tulip

from .framing import *
from .handshake import *
from .http import read_request


@tulip.task
def serve(ws_handler, host=None, port=None, protocols=(), extensions=()):
    """
    Serve a WebSocket handler.

    `ws_handler` must be a coroutine, and it's called with the WebSocket
    protocol and the request URI in arguments.
    """
    assert not protocols, "protocols aren't supported"
    assert not extensions, "extensions aren't supported"

    yield from tulip.get_event_loop().start_serving(
            lambda: WebSocketServerProtocol(ws_handler), host, port)


class WebSocketServerProtocol(WebSocketFramingProtocol):
    """
    Sample WebSocket server implementation as a Tulip protocol.

    For the sake of simplicity, this protocol doesn't inherit a proper HTTP
    implementation. It doesn't send appropriate HTTP responses when something
    goes wrong.
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
        Perform the WebSocket opening handshake.

        Raise `InvalidHandshake` if the handshake fails.
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
        build_response(set_header, key)
        response.append('\r\n')
        response = '\r\n'.join(response).encode()
        self.transport.write(response)

        return uri
