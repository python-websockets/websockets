"""
The :mod:`websockets.uri` module implements parsing of WebSocket URIs
according to `section 3 of RFC 6455`_.

.. _section 3 of RFC 6455: http://tools.ietf.org/html/rfc6455#section-3

"""

import collections
import urllib.parse

from .exceptions import InvalidURI


__all__ = [
    'parse_uri', 'WebSocketURI',
    'parse_proxy_uri', 'ProxyURI',
]

WebSocketURI = collections.namedtuple(
    'WebSocketURI', ['secure', 'host', 'port', 'resource_name', 'user_info'])
WebSocketURI.__doc__ = """WebSocket URI.

* ``secure`` is the secure flag
* ``host`` is the lower-case host
* ``port`` if the integer port, it's always provided even if it's the default
* ``resource_name`` is the resource name, that is, the path and optional query
* ``user_info`` is an ``(username, password)`` tuple when the URI contains
  `User Information`_, else ``None``.

.. _User Information: https://tools.ietf.org/html/rfc3986#section-3.2.1

"""

ProxyURI = collections.namedtuple(
    'ProxyURI', ['secure', 'host', 'port', 'user_info'])
ProxyURI.__doc__ = """Proxy URI.

* ``secure`` tells whether to connect to the proxy with TLS
* ``host`` is the lower-case host
* ``port`` if the integer port, it's always provided even if it's the default
* ``user_info`` is an ``(username, password)`` tuple when the URI contains
  `User Information`_, else ``None``.

.. _User Information: https://tools.ietf.org/html/rfc3986#section-3.2.1

"""


def parse_uri(uri):
    """
    This function parses and validates a WebSocket URI.

    If the URI is valid, it returns a :class:`WebSocketURI`.

    Otherwise it raises an :exc:`~websockets.exceptions.InvalidURI` exception.

    """
    uri = urllib.parse.urlparse(uri)
    try:
        assert uri.scheme in ['ws', 'wss']
        assert uri.hostname is not None
        # Params aren't allowed ws or wss URLs. urlparse doesn't extract them.
        assert uri.params == ''
        assert uri.fragment == ''
    except AssertionError as exc:
        raise InvalidURI("{} isn't a valid URI".format(uri)) from exc

    secure = uri.scheme == 'wss'
    host = uri.hostname
    port = uri.port or (443 if secure else 80)
    resource_name = uri.path or '/'
    if uri.query:
        resource_name += '?' + uri.query
    user_info = None
    if uri.username or uri.password:
        user_info = (uri.username, uri.password)
    return WebSocketURI(secure, host, port, resource_name, user_info)


def parse_proxy_uri(uri):
    """
    This function parses and validates a HTTP proxy URI.

    If the URI is valid, it returns a :class:`ProxyURI`.

    Otherwise it raises an :exc:`~websockets.exceptions.InvalidURI` exception.

    """
    uri = urllib.parse.urlparse(uri)
    try:
        assert uri.scheme in ['http', 'https']
        assert uri.hostname is not None
        assert uri.path == ''
        assert uri.params == ''
        assert uri.query == ''
        assert uri.fragment == ''
    except AssertionError as exc:
        raise InvalidURI("{} isn't a valid URI".format(uri)) from exc

    secure = uri.scheme == 'https'
    host = uri.hostname
    port = uri.port or (443 if secure else 80)
    user_info = None
    if uri.username or uri.password:
        user_info = (uri.username, uri.password)
    return ProxyURI(secure, host, port, user_info)
