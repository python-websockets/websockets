"""
The :mod:`websockets.server` module defines a simple WebSocket server API.
"""

__all__ = ['serve', 'WebSocketServerProtocol']

import logging

import tulip

from .exceptions import InvalidHandshake
from .handshake import check_request, build_response
from .http import read_request, USER_AGENT
from .protocol import WebSocketCommonProtocol


logger = logging.getLogger()


class WebSocketServerProtocol(WebSocketCommonProtocol):
    """
    Complete WebSocket server implementation as a Tulip protocol.

    TODO: for the sake of simplicity, this protocol doesn't inherit a proper
    HTTP implementation, and it doesn't send appropriate HTTP responses when
    something goes wrong.
    """

    state = 'CONNECTING'

    def __init__(self, ws_handler=None, *args, **kwargs):
        self.ws_handler = ws_handler
        super().__init__(*args, **kwargs)

    def connection_made(self, transport):
        super().connection_made(transport)
        self.handler()

    @tulip.task
    def handler(self):
        try:
            if self.ws_handler is None:                     # pragma: no cover
                raise NotImplementedError
            uri = yield from self.handshake()
            yield from self.ws_handler(self, uri)
            yield from self.close()
        except Exception:
            logger.warning("Exception in connection handler", exc_info=True)
            self.transport.close()
            return

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

        self.state = 'OPEN'
        self.opening_handshake.set_result(True)

        return uri


@tulip.task
def serve(ws_handler, host=None, port=None, *,
          protocols=(), extensions=(), klass=WebSocketServerProtocol, **kwds):
    """
    This task starts a WebSocket server.

    It's a thin wrapper around the event loop's ``start_serving`` method.

    `ws_handler` is the WebSocket handler. It must be a coroutine accepting
    two arguments: a :class:`~websockets.framing.WebSocketServerProtocol` and
    the request URI. The `host` and `port` arguments and other keyword
    arguments are passed to ``start_serving``. The return value is a list of
    objects that can be passed to ``stop_serving``.

    Whenever a client connects, the server accepts the connection, creates a
    :class:`~websockets.framing.WebSocketServerProtocol`, performs the opening
    handshake, and delegates to the WebSocket handler. Once the handler
    completes, the server performs the closing handshake and closes the
    connection.
    """
    assert not protocols, "protocols aren't supported"
    assert not extensions, "extensions aren't supported"

    return (yield from tulip.get_event_loop().start_serving(
            lambda: klass(ws_handler), host, port, **kwds))


# Workaround for http://code.google.com/p/tulip/issues/detail?id=30
__serve_doc__ = serve.__doc__
serve = tulip.task(serve)
serve.__doc__ = __serve_doc__
