"""
WebSocket URIs (part 3 of RFC 6455).
"""

__all__ = ['InvalidURI', 'parse_uri']

import collections
import urllib.parse


class InvalidURI(Exception):
    """Exception raised when an URI is invalid."""


WebSocketURI = collections.namedtuple('WebSocketURI',
        ('secure', 'host', 'port', 'resource_name'))


def parse_uri(uri):
    """
    Parse and validate a WebSocket URI.

    If the URI is valid, this function returns a namedtuple (secure, host,
    port, resource_name). Otherwise it raises an `InvalidURI` exception.
    """
    uri = urllib.parse.urlparse(uri)
    try:
        assert uri.scheme in ('ws', 'wss')
        assert uri.params == ''
        assert uri.fragment == ''
        assert uri.username is None
        assert uri.password is None
        assert uri.hostname is not None
    except AssertionError as exc:
        raise InvalidURI() from exc

    secure = uri.scheme == 'wss'
    host = uri.hostname
    port = uri.port or (443 if secure else 80)
    resource_name = uri.path or '/'
    if uri.query:
        resource_name += '?' + uri.query
    return WebSocketURI(secure, host, port, resource_name)
