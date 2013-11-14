"""
The :mod:`websockets.client` module defines a simple WebSocket client API.
"""

__all__ = ['connect', 'WebSocketClientProtocol']

import asyncio

from .exceptions import InvalidHandshake
from .handshake import build_request, check_response
from .http import read_response, USER_AGENT
from .protocol import WebSocketCommonProtocol
from .uri import parse_uri


class WebSocketClientProtocol(WebSocketCommonProtocol):
    """
    Complete WebSocket client implementation as a Tulip protocol.

    This class inherits most of its methods from
    :class:`~websockets.protocol.WebSocketCommonProtocol`.
    """

    is_client = True
    state = 'CONNECTING'

    @asyncio.coroutine
    def handshake(self, uri):
        """
        Perform the client side of the opening handshake.
        """
        # Send handshake request. Since the uri and the headers only contain
        # ASCII characters, we can keep this simple.
        request = ['GET %s HTTP/1.1' % uri.resource_name]
        set_header = lambda k, v: request.append('{}: {}'.format(k, v))
        if uri.port == (443 if uri.secure else 80):         # pragma: no cover
            set_header('Host', uri.host)
        else:
            set_header('Host', '{}:{}'.format(uri.host, uri.port))
        set_header('User-Agent', USER_AGENT)
        key = build_request(set_header)
        request.append('\r\n')
        request = '\r\n'.join(request).encode()
        self.transport.write(request)

        # Read handshake response.
        try:
            status_code, headers = yield from read_response(self.stream)
        except Exception as exc:
            raise InvalidHandshake("Malformed HTTP message") from exc
        if status_code != 101:
            raise InvalidHandshake("Bad status code: {}".format(status_code))
        get_header = lambda k: headers.get(k, '')
        check_response(get_header, key)

        self.state = 'OPEN'
        self.opening_handshake.set_result(True)


@asyncio.coroutine
def connect(uri, *,
            klass=WebSocketClientProtocol, **kwds):
    """
    This coroutine connects to a WebSocket server.

    It's a thin wrapper around the event loop's ``create_connection`` method.
    Extra keyword arguments are passed to ``create_server``.

    It returns a :class:`~websockets.client.WebSocketClientProtocol` which can
    then be used to send and receive messages.

    It raises :exc:`~websockets.uri.InvalidURI` if `uri` is invalid and
    :exc:`~websockets.handshake.InvalidHandshake` if the handshake fails.

    Clients shouldn't close the WebSocket connection. Instead, they should
    wait until the server performs the closing handshake by yielding from the
    protocol's :attr:`worker` attribute.

    :func:`connect` implements the sequence called "Establish a WebSocket
    Connection" in RFC 6455, except for the requirement that "there MUST be no
    more than one connection in a CONNECTING state."
    """
    uri = parse_uri(uri)
    kwds.setdefault('ssl', uri.secure)
    transport, protocol = yield from asyncio.get_event_loop().create_connection(
            klass, uri.host, uri.port, **kwds)

    try:
        yield from protocol.handshake(uri)
    except Exception:
        transport.close()
        raise

    return protocol
