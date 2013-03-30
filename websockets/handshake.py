"""
Phase one: the opening handshake (part 4 of RFC 6455).

This module provides functions to implement the WebSocket opening handshake
with an existing HTTP library. Some checks cannot be performed because they
depend too much on the library being used; instead, they're described in the
docstrings.

This module currently has the following limitations:
- it doesn't support protocols or extensions.
"""

__all__ = [
    'InvalidHandshake',
    'build_request', 'check_request',
    'build_response', 'check_response',
]

import base64
import hashlib
import random


GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class InvalidHandshake(Exception):
    """Exception raised when a handshake request or response is invalid."""


def build_request(set_header):
    """
    Build a handshake request to send to the server.

    `set_headers` is a function accepting a header name as a `str` and a
    header value as a `str`.
    """
    rand = bytes(random.getrandbits(8) for _ in range(16))
    key = base64.b64encode(rand).decode()
    set_header('Upgrade', 'WebSocket')
    set_header('Connection', 'Upgrade')
    set_header('Sec-WebSocket-Key', key)
    set_header('Sec-WebSocket-Version', '13')
    return key


def check_request(get_header):
    """
    Check a handshake request received from the client.

    `get_headers` is a function accepting a header name as a `str` and
    returning the header value as a `str`.

    If the handshake is valid, this function returns the WebSocket key, which
    can be used to build the handshake response. Otherwise, it raises an
    `InvalidHandshake` exception and the server must return an error, usually
    400 Bad Request.

    This function doesn't verify that the request is an HTTP/1.1 or higher GET
    request and doesn't perform Host and Origin checks. These controls are
    usually performed earlier in the HTTP request handling code. They're the
    responsibility of the caller.
    """
    try:
        assert get_header('Upgrade').lower() == 'websocket'
        assert any(token.strip() == 'upgrade'
                for token in get_header('Connection').lower().split(','))
        key = get_header('Sec-WebSocket-Key')
        assert len(base64.b64decode(key.encode())) == 16
        assert get_header('Sec-WebSocket-Version') == '13'
        return key
    except (AssertionError, KeyError) as exc:
        raise InvalidHandshake() from exc


def build_response(set_header, key):
    """
    Build a handshake response to send to the client.

    `set_headers` is a function accepting a header name as a `str` and a
    header value as a `str`. `key` is the result of `check_request`.
    """
    set_header('Upgrade', 'WebSocket')
    set_header('Connection', 'Upgrade')
    set_header('Sec-WebSocket-Accept', accept(key))


def check_response(get_header, key):
    """
    Check a handshake response received from the server.

    `get_headers` is a function accepting a header name as a `str` and
    returning the header value as a `str`. `key` is the result of
    `build_request`.

    If the handshake is valid, this function returns `None`. Otherwise, it
    raises an `InvalidHandshake` exception.
    """
    try:
        assert get_header('Upgrade').lower() == 'websocket'
        assert any(token.strip() == 'upgrade'
                for token in get_header('Connection').lower().split(','))
        assert get_header('Sec-WebSocket-Accept') == accept(key)
    except (AssertionError, KeyError) as exc:
        raise InvalidHandshake() from exc


def accept(key):
    sha1 = hashlib.sha1((key + GUID).encode()).digest()
    return base64.b64encode(sha1).decode()
