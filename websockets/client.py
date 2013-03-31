"""
Sample WebSocket client implementation.

It demonstrates how to tie together the handshake and framing APIs.
"""

__all__ = ['connect', 'WebSocketClientProtocol']

import tulip

from .framing import *
from .handshake import *
from .http import read_response
from .uri import *


@tulip.coroutine
def connect(uri, protocols=(), extensions=()):
    """
    Connect to a WebSocket URI. Return a `WebSocketClientProtocol`.

    This is described as Establish a WebSocket Connection in RFC 6455.

    The following requirements aren't implemented:

    - There MUST be no more than one connection in a CONNECTING state.
    - Clients MUST use the Server Name Indication extension. (Tulip doesn't
      support passing a server_hostname argument to the wrap_socket() call.)
    """
    assert not protocols, "protocols aren't supported"
    assert not extensions, "extensions aren't supported"

    uri = parse_uri(uri)
    transport, protocol = yield from tulip.get_event_loop().create_connection(
            WebSocketClientProtocol, uri.host, uri.port, ssl=uri.secure)

    try:
        yield from protocol.handshake(uri)
    except Exception:
        transport.close()
        raise

    return protocol


class WebSocketClientProtocol(WebSocketFramingProtocol):
    """
    Sample WebSocket client implementation as a Tulip protocol.
    """

    def __init__(self, *args, **kwargs):
        kwargs['is_client'] = True
        super().__init__(*args, **kwargs)

    @tulip.coroutine
    def handshake(self, uri):
        """
        Perform the WebSocket opening handshake.

        Raise `InvalidHandshake` if the handshake fails.
        """
        # Send handshake request. Since the uri and the headers only contain
        # ASCII characters, we can keep this simple.
        request = ['GET %s HTTP/1.1' % uri.resource_name]
        set_header = lambda k, v: request.append('{}: {}'.format(k, v))
        if uri.port == (443 if uri.secure else 80):
            set_header('Host', uri.host)
        else:
            set_header('Host', '{}:{}'.format(uri.host, uri.port))
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
            raise InvalidHandshake("Unexpected status code")
        get_header = lambda k: headers.get(k, '')
        check_response(get_header, key)
