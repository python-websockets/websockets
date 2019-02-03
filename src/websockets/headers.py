"""
The :mod:`websockets.headers` module provides parsers and serializers for HTTP
headers used in WebSocket handshake messages.

Its functions cannot be imported from :mod:`websockets`. They must be imported
from :mod:`websockets.headers`.

"""

import base64
import re
from typing import Callable, List, NewType, Optional, Sequence, Tuple, TypeVar, cast

from .exceptions import InvalidHeaderFormat
from .typing import ExtensionHeader, ExtensionParameter, Subprotocol


__all__ = [
    "parse_connection",
    "parse_upgrade",
    "parse_extension",
    "build_extension",
    "parse_subprotocol",
    "build_subprotocol",
]


T = TypeVar("T")

ConnectionOption = NewType("ConnectionOption", str)
UpgradeProtocol = NewType("UpgradeProtocol", str)


# To avoid a dependency on a parsing library, we implement manually the ABNF
# described in https://tools.ietf.org/html/rfc6455#section-9.1 with the
# definitions from https://tools.ietf.org/html/rfc7230#appendix-B.


def peek_ahead(header: str, pos: int) -> Optional[str]:
    """
    Return the next character from ``header`` at the given position.

    Return ``None`` at the end of ``header``.

    We never need to peek more than one character ahead.

    """
    return None if pos == len(header) else header[pos]


_OWS_re = re.compile(r"[\t ]*")


def parse_OWS(header: str, pos: int) -> int:
    """
    Parse optional whitespace from ``header`` at the given position.

    Return the new position.

    The whitespace itself isn't returned because it isn't significant.

    """
    # There's always a match, possibly empty, whose content doesn't matter.
    match = _OWS_re.match(header, pos)
    assert match is not None
    return match.end()


_token_re = re.compile(r"[-!#$%&\'*+.^_`|~0-9a-zA-Z]+")


def parse_token(header: str, pos: int, header_name: str) -> Tuple[str, int]:
    """
    Parse a token from ``header`` at the given position.

    Return the token value and the new position.

    Raise :exc:`~websockets.exceptions.InvalidHeaderFormat` on invalid inputs.

    """
    match = _token_re.match(header, pos)
    if match is None:
        raise InvalidHeaderFormat(header_name, "expected token", header, pos)
    return match.group(), match.end()


_quoted_string_re = re.compile(
    r'"(?:[\x09\x20-\x21\x23-\x5b\x5d-\x7e]|\\[\x09\x20-\x7e\x80-\xff])*"'
)


_unquote_re = re.compile(r"\\([\x09\x20-\x7e\x80-\xff])")


def parse_quoted_string(header: str, pos: int, header_name: str) -> Tuple[str, int]:
    """
    Parse a quoted string from ``header`` at the given position.

    Return the unquoted value and the new position.

    Raise :exc:`~websockets.exceptions.InvalidHeaderFormat` on invalid inputs.

    """
    match = _quoted_string_re.match(header, pos)
    if match is None:
        raise InvalidHeaderFormat(header_name, "expected quoted string", header, pos)
    return _unquote_re.sub(r"\1", match.group()[1:-1]), match.end()


def parse_list(
    parse_item: Callable[[str, int, str], Tuple[T, int]],
    header: str,
    pos: int,
    header_name: str,
) -> List[T]:
    """
    Parse a comma-separated list from ``header`` at the given position.

    This is appropriate for parsing values with the following grammar:

        1#item

    ``parse_item`` parses one item.

    ``header`` is assumed not to start or end with whitespace.

    (This function is designed for parsing an entire header value and
    :func:`~websockets.http.read_headers` strips whitespace from values.)

    Return a list of items.

    Raise :exc:`~websockets.exceptions.InvalidHeaderFormat` on invalid inputs.

    """
    # Per https://tools.ietf.org/html/rfc7230#section-7, "a recipient MUST
    # parse and ignore a reasonable number of empty list elements"; hence
    # while loops that remove extra delimiters.

    # Remove extra delimiters before the first item.
    while peek_ahead(header, pos) == ",":
        pos = parse_OWS(header, pos + 1)

    items = []
    while True:
        # Loop invariant: a item starts at pos in header.
        item, pos = parse_item(header, pos, header_name)
        items.append(item)
        pos = parse_OWS(header, pos)

        # We may have reached the end of the header.
        if pos == len(header):
            break

        # There must be a delimiter after each element except the last one.
        if peek_ahead(header, pos) == ",":
            pos = parse_OWS(header, pos + 1)
        else:
            raise InvalidHeaderFormat(header_name, "expected comma", header, pos)

        # Remove extra delimiters before the next item.
        while peek_ahead(header, pos) == ",":
            pos = parse_OWS(header, pos + 1)

        # We may have reached the end of the header.
        if pos == len(header):
            break

    # Since we only advance in the header by one character with peek_ahead()
    # or with the end position of a regex match, we can't overshoot the end.
    assert pos == len(header)

    return items


def parse_connection_option(
    header: str, pos: int, header_name: str
) -> Tuple[ConnectionOption, int]:
    """
    Parse a Connection option from ``header`` at the given position.

    Return the protocol value and the new position.

    Raise :exc:`~websockets.exceptions.InvalidHeaderFormat` on invalid inputs.

    """
    item, pos = parse_token(header, pos, header_name)
    return cast(ConnectionOption, item), pos


def parse_connection(header: str) -> List[ConnectionOption]:
    """
    Parse a ``Connection`` header.

    Return a list of connection options.

    Raise :exc:`~websockets.exceptions.InvalidHeaderFormat` on invalid inputs.

    """
    return parse_list(parse_connection_option, header, 0, "Connection")


_protocol_re = re.compile(
    r"[-!#$%&\'*+.^_`|~0-9a-zA-Z]+(?:/[-!#$%&\'*+.^_`|~0-9a-zA-Z]+)?"
)


def parse_upgrade_protocol(
    header: str, pos: int, header_name: str
) -> Tuple[UpgradeProtocol, int]:
    """
    Parse an Upgrade protocol from ``header`` at the given position.

    Return the protocol value and the new position.

    Raise :exc:`~websockets.exceptions.InvalidHeaderFormat` on invalid inputs.

    """
    match = _protocol_re.match(header, pos)
    if match is None:
        raise InvalidHeaderFormat(header_name, "expected protocol", header, pos)
    return cast(UpgradeProtocol, match.group()), match.end()


def parse_upgrade(header: str) -> List[UpgradeProtocol]:
    """
    Parse an ``Upgrade`` header.

    Return a list of protocols.

    Raise :exc:`~websockets.exceptions.InvalidHeaderFormat` on invalid inputs.

    """
    return parse_list(parse_upgrade_protocol, header, 0, "Upgrade")


def parse_extension_item_param(
    header: str, pos: int, header_name: str
) -> Tuple[ExtensionParameter, int]:
    """
    Parse a single extension parameter from ``header`` at the given position.

    Return a ``(name, value)`` pair and the new position.

    Raise :exc:`~websockets.exceptions.InvalidHeaderFormat` on invalid inputs.

    """
    # Extract parameter name.
    name, pos = parse_token(header, pos, header_name)
    pos = parse_OWS(header, pos)
    # Extract parameter value, if there is one.
    value: Optional[str] = None
    if peek_ahead(header, pos) == "=":
        pos = parse_OWS(header, pos + 1)
        if peek_ahead(header, pos) == '"':
            pos_before = pos  # for proper error reporting below
            value, pos = parse_quoted_string(header, pos, header_name)
            # https://tools.ietf.org/html/rfc6455#section-9.1 says: the value
            # after quoted-string unescaping MUST conform to the 'token' ABNF.
            if _token_re.fullmatch(value) is None:
                raise InvalidHeaderFormat(
                    header_name, "invalid quoted header content", header, pos_before
                )
        else:
            value, pos = parse_token(header, pos, header_name)
        pos = parse_OWS(header, pos)

    return (name, value), pos


def parse_extension_item(
    header: str, pos: int, header_name: str
) -> Tuple[ExtensionHeader, int]:
    """
    Parse an extension definition from ``header`` at the given position.

    Return an ``(extension name, parameters)`` pair, where ``parameters`` is a
    list of ``(name, value)`` pairs, and the new position.

    Raise :exc:`~websockets.exceptions.InvalidHeaderFormat` on invalid inputs.

    """
    # Extract extension name.
    name, pos = parse_token(header, pos, header_name)
    pos = parse_OWS(header, pos)
    # Extract all parameters.
    parameters = []
    while peek_ahead(header, pos) == ";":
        pos = parse_OWS(header, pos + 1)
        parameter, pos = parse_extension_item_param(header, pos, header_name)
        parameters.append(parameter)
    return (name, parameters), pos


def parse_extension(header: str) -> List[ExtensionHeader]:
    """
    Parse a ``Sec-WebSocket-Extensions`` header.

    Return a value with the following format::

        [
            (
                'extension name',
                [
                    ('parameter name', 'parameter value'),
                    ....
                ]
            ),
            ...
        ]

    Parameter values are ``None`` when no value is provided.

    Raise :exc:`~websockets.exceptions.InvalidHeaderFormat` on invalid inputs.

    """
    return parse_list(parse_extension_item, header, 0, "Sec-WebSocket-Extensions")


parse_extension_list = parse_extension  # alias for backwards-compatibility


def build_extension_item(name: str, parameters: List[ExtensionParameter]) -> str:
    """
    Build an extension definition.

    This is the reverse of :func:`parse_extension_item`.

    """
    return "; ".join(
        [name]
        + [
            # Quoted strings aren't necessary because values are always tokens.
            name if value is None else f"{name}={value}"
            for name, value in parameters
        ]
    )


def build_extension(extensions: Sequence[ExtensionHeader]) -> str:
    """
    Unparse a ``Sec-WebSocket-Extensions`` header.

    This is the reverse of :func:`parse_extension`.

    """
    return ", ".join(
        build_extension_item(name, parameters) for name, parameters in extensions
    )


build_extension_list = build_extension  # alias for backwards-compatibility


def parse_subprotocol_item(
    header: str, pos: int, header_name: str
) -> Tuple[Subprotocol, int]:
    """
    Parse a subprotocol from ``header`` at the given position.

    Return the subprotocol value and the new position.

    Raise :exc:`~websockets.exceptions.InvalidHeaderFormat` on invalid inputs.

    """
    item, pos = parse_token(header, pos, header_name)
    return cast(Subprotocol, item), pos


def parse_subprotocol(header: str) -> List[Subprotocol]:
    """
    Parse a ``Sec-WebSocket-Protocol`` header.

    Raise :exc:`~websockets.exceptions.InvalidHeaderFormat` on invalid inputs.

    """
    return parse_list(parse_subprotocol_item, header, 0, "Sec-WebSocket-Protocol")


parse_subprotocol_list = parse_subprotocol  # alias for backwards-compatibility


def build_subprotocol(protocols: Sequence[Subprotocol]) -> str:
    """
    Unparse a ``Sec-WebSocket-Protocol`` header.

    This is the reverse of :func:`parse_subprotocol`.

    """
    return ", ".join(protocols)


build_subprotocol_list = build_subprotocol  # alias for backwards-compatibility


def build_basic_auth(username: str, password: str) -> str:
    """
    Build an Authorization header for HTTP Basic Auth.

    """
    # https://tools.ietf.org/html/rfc7617#section-2
    assert ":" not in username
    user_pass = f"{username}:{password}"
    basic_credentials = base64.b64encode(user_pass.encode()).decode()
    return "Basic " + basic_credentials