"""
The :mod:`websockets.uri` module implements parsing of WebSocket URIs
according to `section 3 of RFC 6455`_.

.. _section 3 of RFC 6455: http://tools.ietf.org/html/rfc6455#section-3

"""

import urllib.parse
from typing import NamedTuple, Optional, Tuple

from .exceptions import InvalidURI


__all__ = ["parse_uri", "WebSocketURI"]


# Consider converting to a dataclass when dropping support for Python < 3.7.


class WebSocketURI(NamedTuple):
    secure: bool
    host: str
    port: int
    resource_name: str
    user_info: Optional[Tuple[str, str]]


# Declare the docstring normally when dropping support for Python < 3.6.1.

WebSocketURI.__doc__ = """
WebSocket URI.

* ``secure`` is the secure flag
* ``host`` is the lower-case host
* ``port`` if the integer port, it's always provided even if it's the default
* ``resource_name`` is the resource name, that is, the path and optional query
* ``user_info`` is an ``(username, password)`` tuple when the URI contains
  `User Information`_, else ``None``.

.. _User Information: https://tools.ietf.org/html/rfc3986#section-3.2.1

"""


def parse_uri(uri: str) -> WebSocketURI:
    """
    This function parses and validates a WebSocket URI.

    If the URI is valid, it returns a :class:`WebSocketURI`.

    Otherwise it raises an :exc:`~websockets.exceptions.InvalidURI` exception.

    """
    parsed = urllib.parse.urlparse(uri)
    try:
        assert parsed.scheme in ["ws", "wss"]
        assert parsed.params == ""
        assert parsed.fragment == ""
        assert parsed.hostname is not None
    except AssertionError as exc:
        raise InvalidURI(uri) from exc

    secure = parsed.scheme == "wss"
    host = parsed.hostname
    port = parsed.port or (443 if secure else 80)
    resource_name = parsed.path or "/"
    if parsed.query:
        resource_name += "?" + parsed.query
    user_info = None
    if parsed.username or parsed.password:
        user_info = (parsed.username, parsed.password)
    return WebSocketURI(secure, host, port, resource_name, user_info)
