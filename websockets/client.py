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
    Complete WebSocket client implementation as an asyncio protocol.

    This class inherits most of its methods from
    :class:`~websockets.protocol.WebSocketCommonProtocol`.
    """

    is_client = True
    state = 'CONNECTING'

    @asyncio.coroutine
    def handshake(self, wsuri, origin=None):
        """
        Perform the client side of the opening handshake.

        If provided, ``origin`` sets the HTTP Origin header.
        """
        headers = []
        set_header = lambda k, v: headers.append((k, v))
        if wsuri.port == (443 if wsuri.secure else 80):         # pragma: no cover
            set_header('Host', wsuri.host)
        else:
            set_header('Host', '{}:{}'.format(wsuri.host, wsuri.port))
        if origin is not None:
            set_header('Origin', origin)
        set_header('User-Agent', USER_AGENT)
        key = build_request(set_header)
        self.raw_request_headers = headers

        # Send handshake request. Since the URI and the headers only contain
        # ASCII characters, we can keep this simple.
        request = ['GET %s HTTP/1.1' % wsuri.resource_name]
        request.extend('{}: {}'.format(k, v) for k, v in headers)
        request.append('\r\n')
        request = '\r\n'.join(request).encode()
        self.writer.write(request)

        # Read handshake response.
        try:
            status_code, headers = yield from read_response(self.reader)
        except Exception as exc:
            raise InvalidHandshake("Malformed HTTP message") from exc
        if status_code != 101:
            raise InvalidHandshake("Bad status code: {}".format(status_code))
        self.raw_response_headers = list(headers.raw_items())
        get_header = lambda k: headers.get(k, '')
        check_response(get_header, key)

        self.state = 'OPEN'
        self.opening_handshake.set_result(True)


@asyncio.coroutine
def connect(uri, *,
            klass=WebSocketClientProtocol, origin=None, **kwds):
    """
    This coroutine connects to a WebSocket server.

    It accepts an ``origin`` keyword argument to set the Origin HTTP header.

    It's a thin wrapper around the event loop's `create_connection` method.
    Extra keyword arguments are passed to `create_server`.

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
    wsuri = parse_uri(uri)
    if wsuri.secure:
        kwds.setdefault('ssl', True)
    elif 'ssl' in kwds:
        raise ValueError("connect() received a SSL context for a ws:// URI. "
                         "Use a wss:// URI to enable TLS.")
    factory = lambda: klass(host=wsuri.host, port=wsuri.port, secure=wsuri.secure)
    transport, protocol = yield from asyncio.get_event_loop().create_connection(
            factory, wsuri.host, wsuri.port, **kwds)

    try:
        yield from protocol.handshake(wsuri, origin=origin)
    except Exception:
        protocol.writer.close()
        raise

    return protocol
