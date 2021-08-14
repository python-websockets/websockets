from __future__ import annotations

import dataclasses
import urllib.parse
from typing import Optional, Tuple

from . import exceptions


__all__ = ["parse_uri", "WebSocketURI"]


@dataclasses.dataclass
class WebSocketURI:
    """
    WebSocket URI.

    Attributes:
        secure: :obj:`True` for a ``wss`` URI, :obj:`False` for a ``ws`` URI.
        host: Host, normalized to lower case.
        port: Port, always set even if it's the default.
        resource_name: Path and optional query.
        user_info: ``(username, password)`` when the URI contains
            `User Information`_, else :obj:`None`.

    .. _User Information: https://www.rfc-editor.org/rfc/rfc3986.html#section-3.2.1

    """

    secure: bool
    host: str
    port: int
    resource_name: str
    user_info: Optional[Tuple[str, str]] = None


# All characters from the gen-delims and sub-delims sets in RFC 3987.
DELIMS = ":/?#[]@!$&'()*+,;="


def parse_uri(uri: str) -> WebSocketURI:
    """
    Parse and validate a WebSocket URI.

    Args:
        uri: WebSocket URI.

    Raises:
        InvalidURI: if ``uri`` isn't a valid WebSocket URI.

    """
    parsed = urllib.parse.urlparse(uri)
    if parsed.scheme not in ["ws", "wss"]:
        raise exceptions.InvalidURI(uri, "scheme isn't ws or wss")
    if parsed.hostname is None:
        raise exceptions.InvalidURI(uri, "hostname isn't provided")
    if parsed.fragment != "":
        raise exceptions.InvalidURI(uri, "fragment identifier is meaningless")

    secure = parsed.scheme == "wss"
    host = parsed.hostname
    port = parsed.port or (443 if secure else 80)
    resource_name = parsed.path or "/"
    if parsed.query:
        resource_name += "?" + parsed.query
    user_info = None
    if parsed.username is not None:
        # urllib.parse.urlparse accepts URLs with a username but without a
        # password. This doesn't make sense for HTTP Basic Auth credentials.
        if parsed.password is None:
            raise exceptions.InvalidURI(uri, "username provided without password")
        user_info = (parsed.username, parsed.password)

    try:
        uri.encode("ascii")
    except UnicodeEncodeError:
        # Input contains non-ASCII characters.
        # It must be an IRI. Convert it to a URI.
        host = host.encode("idna").decode()
        resource_name = urllib.parse.quote(resource_name, safe=DELIMS)
        if user_info is not None:
            user_info = (
                urllib.parse.quote(user_info[0], safe=DELIMS),
                urllib.parse.quote(user_info[1], safe=DELIMS),
            )

    return WebSocketURI(secure, host, port, resource_name, user_info)
