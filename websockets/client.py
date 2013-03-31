"""
Sample WebSocket client implementation.

It is simplistic, and in particular, it doesn't use an HTTP parsing library.
This is only designed for testing the server side, and to demonstrate how to
use build_request and check_response.
"""

__all__ = ['connect', 'WebSocketClientProtocol']

import tulip

from .framing import *
from .handshake import *
from .uri import *


@tulip.coroutine
def connect(uri, protocols=(), extensions=()):
    """
    Connect to a WebSocket URI.

    This is described as _Establish a WebSocket Connection_ in RFC 6455.

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
        CRLF = '\r\n'
        # Send handshake request.
        request = ['GET %s HTTP/1.1' % uri.resource_name]
        set_header = lambda k, v: request.append('{}: {}'.format(k, v))
        if uri.port == (443 if uri.secure else 80):
            set_header('Host', uri.host)
        else:
            set_header('Host', '{}:{}'.format(uri.host, uri.port))
        key = build_request(set_header)
        request.append(CRLF)
        request = CRLF.join(request).encode()
        self.transport.write(request)

        # Read handshake response. Very, very simplistic.
        status_line = (yield from self.stream.readline()).decode()
        if not status_line.endswith(CRLF):
            raise InvalidHandshake("Bad line")
        if not status_line.startswith('HTTP/1.1 101 '):
            raise InvalidHandshake("Bad status")
        headers = {}
        while True:
            header_line = (yield from self.stream.readline()).decode()
            if header_line == CRLF:
                break
            if not header_line.endswith(CRLF):
                raise InvalidHandshake("Bad line")
            name, value = header_line.split(':', 1)
            headers[name.lower()] = value.strip()
        get_header = lambda k: headers[k.lower()]
        check_response(get_header, key)
