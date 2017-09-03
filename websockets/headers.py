"""
The :mod:`websockets.headers` module provides parsers and serializers for HTTP
headers used in WebSocket handshake messages.

Its functions cannot be imported from :mod:`websockets`. They must be imported
from :mod:`websockets.headers`.

"""

import re

from .exceptions import InvalidHeader


__all__ = [
    'parse_extension_list', 'build_extension_list',
    'parse_protocol_list', 'build_protocol_list',
]


# To avoid a dependency on a parsing library, we implement manually the ABNF
# described in https://tools.ietf.org/html/rfc6455#section-9.1 with the
# definitions from https://tools.ietf.org/html/rfc7230#appendix-B.

def peek_ahead(string, pos):
    # We never peek more than one character ahead.
    return None if pos == len(string) else string[pos]


_OWS_re = re.compile(r'[\t ]*')


def parse_OWS(string, pos):
    # There's always a match, possibly empty, whose content doesn't matter.
    match = _OWS_re.match(string, pos)
    return match.end()


_token_re = re.compile(r'[-!#$%&\'*+.^_`|~0-9a-zA-Z]+')


def parse_token(string, pos):
    match = _token_re.match(string, pos)
    if match is None:
        raise InvalidHeader("expected token", string=string, pos=pos)
    return match.group(), match.end()


_quoted_string_re = re.compile(
    r'"(?:[\x09\x20-\x21\x23-\x5b\x5d-\x7e]|\\[\x09\x20-\x7e\x80-\xff])*"')


_unquote_re = re.compile(r'\\([\x09\x20-\x7e\x80-\xff])')


def parse_quoted_string(string, pos):
    match = _quoted_string_re.match(string, pos)
    if match is None:
        raise InvalidHeader("expected quoted string", string=string, pos=pos)
    return _unquote_re.sub(r'\1', match.group()[1:-1]), match.end()


def parse_extension_param(string, pos):
    # Extract parameter name.
    name, pos = parse_token(string, pos)
    pos = parse_OWS(string, pos)
    # Extract parameter string, if there is one.
    if peek_ahead(string, pos) == '=':
        pos = parse_OWS(string, pos + 1)
        if peek_ahead(string, pos) == '"':
            pos_before = pos    # for proper error reporting below
            value, pos = parse_quoted_string(string, pos)
            # https://tools.ietf.org/html/rfc6455#section-9.1 says: the value
            # after quoted-string unescaping MUST conform to the 'token' ABNF.
            if _token_re.fullmatch(value) is None:
                raise InvalidHeader("invalid quoted string content",
                                    string=string, pos=pos_before)
        else:
            value, pos = parse_token(string, pos)
        pos = parse_OWS(string, pos)
    else:
        value = None

    return (name, value), pos


def parse_extension(string, pos):
    # Extract extension name.
    name, pos = parse_token(string, pos)
    pos = parse_OWS(string, pos)
    # Extract all parameters.
    parameters = []
    while peek_ahead(string, pos) == ';':
        pos = parse_OWS(string, pos + 1)
        parameter, pos = parse_extension_param(string, pos)
        parameters.append(parameter)
    return (name, parameters), pos


def parse_extension_list(string, pos=0):
    """
    Parse a Sec-WebSocket-Extensions header.

    The string is assumed not to start or end with whitespace.

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

    Raise InvalidHeader if the header cannot be parsed.

    """
    # Per https://tools.ietf.org/html/rfc7230#section-7, "a recipient MUST
    # parse and ignore a reasonable number of empty list elements"; hence
    # while loops that remove extra delimiters.

    # Remove extra delimiters before the first extension.
    while peek_ahead(string, pos) == ',':
        pos = parse_OWS(string, pos + 1)

    extensions = []
    while True:
        # Loop invariant: an extension starts at pos in string.
        extension, pos = parse_extension(string, pos)
        extensions.append(extension)

        # We may have reached the end of the string.
        if pos == len(string):
            break

        # There must be a delimiter after each element except the last one.
        if peek_ahead(string, pos) == ',':
            pos = parse_OWS(string, pos + 1)
        else:
            raise InvalidHeader("expected comma", string=string, pos=pos)

        # Remove extra delimiters before the next extension.
        while peek_ahead(string, pos) == ',':
            pos = parse_OWS(string, pos + 1)

        # We may have reached the end of the string.
        if pos == len(string):
            break

    # Since we only advance in the string by one character with peek_ahead()
    # or with the end position of a regex match, we can't overshoot the end.
    assert pos == len(string)

    return extensions


def build_extension(name, parameters):
    return '; '.join([name] + [
        # Quoted strings aren't necessary because values are always tokens.
        name if value is None else '{}={}'.format(name, value)
        for name, value in parameters
    ])


def build_extension_list(extensions):
    """
    Unparse a Sec-WebSocket-Extensions header.

    This is the reverse of parse_extension_list.

    """
    return ', '.join(
        build_extension(name, parameters)
        for name, parameters in extensions
    )


def parse_protocol(string, pos):
    name, pos = parse_token(string, pos)
    pos = parse_OWS(string, pos)
    return name, pos


def parse_protocol_list(string, pos=0):
    """
    Parse a Sec-WebSocket-Protocol header.

    The string is assumed not to start or end with whitespace.

    Return a list of protocols.

    Raise InvalidHeader if the header cannot be parsed.

    """
    # Per https://tools.ietf.org/html/rfc7230#section-7, "a recipient MUST
    # parse and ignore a reasonable number of empty list elements"; hence
    # while loops that remove extra delimiters.

    # Remove extra delimiters before the first extension.
    while peek_ahead(string, pos) == ',':
        pos = parse_OWS(string, pos + 1)

    protocols = []
    while True:
        # Loop invariant: a protocol starts at pos in string.
        protocol, pos = parse_protocol(string, pos)
        protocols.append(protocol)

        # We may have reached the end of the string.
        if pos == len(string):
            break

        # There must be a delimiter after each element except the last one.
        if peek_ahead(string, pos) == ',':
            pos = parse_OWS(string, pos + 1)
        else:
            raise InvalidHeader("expected comma", string=string, pos=pos)

        # Remove extra delimiters before the next protocol.
        while peek_ahead(string, pos) == ',':
            pos = parse_OWS(string, pos + 1)

        # We may have reached the end of the string.
        if pos == len(string):
            break

    # Since we only advance in the string by one character with peek_ahead()
    # or with the end position of a regex match, we can't overshoot the end.
    assert pos == len(string)

    return protocols


def build_protocol_list(protocols):
    """
    Unparse a Sec-WebSocket-Protocol header.

    This is the reverse of parse_protocol_list.

    """
    return ', '.join(protocols)
