"""
The :mod:`websockets.http` module provides HTTP parsing functions. They're
merely adequate for the WebSocket handshake messages. They're used by the
sample client and servers.

These functions cannot be imported from :mod:`websockets`; they must be
imported from :mod:`websockets.http`.
"""

__all__ = ['read_request', 'read_response', 'USER_AGENT']

import email.parser
import io
import sys

import asyncio

from .version import version as websockets_version


MAX_HEADERS = 256
MAX_LINE = 4096

USER_AGENT = ' '.join((
    'Python/{}'.format(sys.version[:3]),
    'websockets/{}'.format(websockets_version),
))


@asyncio.coroutine
def read_request(stream):
    """
    Read an HTTP/1.1 request from `stream`.

    Return `(uri, headers)` where `uri` is a :class:`str` and `headers`
    is a :class:`~email.message.Message`; `uri` isn't URL-decoded.

    Raise an exception if the request isn't well formatted.

    The request is assumed not to contain a body.
    """
    request_line, headers = yield from read_message(stream)
    method, uri, version = request_line[:-2].decode().split(None, 2)
    if method != 'GET':
        raise ValueError("Unsupported method")
    if version != 'HTTP/1.1':
        raise ValueError("Unsupported HTTP version")
    return uri, headers


@asyncio.coroutine
def read_response(stream):
    """
    Read an HTTP/1.1 response from `stream`.

    Return `(status, headers)` where `status` is a :class:`int` and
    `headers` is a :class:`~email.message.Message`.

    Raise an exception if the request isn't well formatted.

    The response is assumed not to contain a body.
    """
    status_line, headers = yield from read_message(stream)
    version, status, reason = status_line[:-2].decode().split(None, 2)
    if version != 'HTTP/1.1':
        raise ValueError("Unsupported HTTP version")
    return int(status), headers


@asyncio.coroutine
def read_message(stream):
    """
    Read an HTTP message from `stream`.

    Return `(start_line, headers)` where `start_line` is :class:`bytes`
    and `headers` is a :class:`~email.message.Message`.

    The message is assumed not to contain a body.
    """
    start_line = yield from read_line(stream)
    header_lines = io.BytesIO()
    for num in range(MAX_HEADERS):
        header_line = yield from read_line(stream)
        header_lines.write(header_line)
        if header_line == b'\r\n':
            break
    else:
        raise ValueError("Too many headers")
    header_lines.seek(0)
    headers = email.parser.BytesHeaderParser().parse(header_lines)
    return start_line, headers


@asyncio.coroutine
def read_line(stream):
    """
    Read a single line from `stream`.
    """
    line = yield from stream.readline()
    if len(line) > MAX_LINE:
        raise ValueError("Line too long")
    if not line.endswith(b'\r\n'):
        raise ValueError("Line without CRLF")
    return line
