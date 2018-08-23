"""
The :mod:`websockets.http` module provides basic HTTP parsing and
serialization. It is merely adequate for WebSocket handshake messages.

Its functions cannot be imported from :mod:`websockets`. They must be imported
from :mod:`websockets.http`.

"""

import asyncio
import collections.abc
import re
import sys

from .version import version as websockets_version


__all__ = [
    'Headers',
    'MultipleValuesError',
    'read_request',
    'read_response',
    'USER_AGENT',
]

MAX_HEADERS = 256
MAX_LINE = 4096

USER_AGENT = 'Python/{} websockets/{}'.format(sys.version[:3], websockets_version)


# See https://tools.ietf.org/html/rfc7230#appendix-B.

# Regex for validating header names.

_token_re = re.compile(rb'[-!#$%&\'*+.^_`|~0-9a-zA-Z]+')

# Regex for validating header values.

# We don't attempt to support obsolete line folding.

# Include HTAB (\x09), SP (\x20), VCHAR (\x21-\x7e), obs-text (\x80-\xff).

# The ABNF is complicated because it attempts to express that optional
# whitespace is ignored. We strip whitespace and don't revalidate that.

# See also https://www.rfc-editor.org/errata_search.php?rfc=7230&eid=4189

_value_re = re.compile(rb'[\x09\x20-\x7e\x80-\xff]*')


@asyncio.coroutine
def read_request(stream):
    """
    Read an HTTP/1.1 GET request from ``stream``.

    ``stream`` is an :class:`~asyncio.StreamReader`.

    Return ``(path, headers)`` where ``path`` is a :class:`str` and
    ``headers`` is a :class:`Headers` instance.

    ``path`` isn't URL-decoded or validated in any way.

    Non-ASCII characters are represented with surrogate escapes.

    Raise an exception if the request isn't well formatted.

    Don't attempt to read the request body because WebSocket handshake
    requests don't have one. If the request contains a body, it may be
    read from ``stream`` after this coroutine returns.

    """
    # https://tools.ietf.org/html/rfc7230#section-3.1.1

    # Parsing is simple because fixed values are expected for method and
    # version and because path isn't checked. Since WebSocket software tends
    # to implement HTTP/1.1 strictly, there's little need for lenient parsing.

    # Given the implementation of read_line(), request_line ends with CRLF.
    request_line = yield from read_line(stream)

    # This may raise "ValueError: not enough values to unpack"
    method, path, version = request_line[:-2].split(b' ', 2)

    if method != b'GET':
        raise ValueError("Unsupported HTTP method: %r" % method)
    if version != b'HTTP/1.1':
        raise ValueError("Unsupported HTTP version: %r" % version)

    path = path.decode('ascii', 'surrogateescape')

    headers = yield from read_headers(stream)

    return path, headers


@asyncio.coroutine
def read_response(stream):
    """
    Read an HTTP/1.1 response from ``stream``.

    ``stream`` is an :class:`~asyncio.StreamReader`.

    Return ``(status_code, headers)`` where ``status_code`` is a :class:`int`
    and ``headers`` is a :class:`Headers` instance.

    Non-ASCII characters are represented with surrogate escapes.

    Raise an exception if the response isn't well formatted.

    Don't attempt to read the response body, because WebSocket handshake
    responses don't have one. If the response contains a body, it may be
    read from ``stream`` after this coroutine returns.

    """
    # https://tools.ietf.org/html/rfc7230#section-3.1.2

    # As in read_request, parsing is simple because a fixed value is expected
    # for version, status_code is a 3-digit number, and reason can be ignored.

    # Given the implementation of read_line(), status_line ends with CRLF.
    status_line = yield from read_line(stream)

    # This may raise "ValueError: not enough values to unpack"
    version, status_code, reason = status_line[:-2].split(b' ', 2)

    if version != b'HTTP/1.1':
        raise ValueError("Unsupported HTTP version: %r" % version)
    # This may raise "ValueError: invalid literal for int() with base 10"
    status_code = int(status_code)
    if not 100 <= status_code < 1000:
        raise ValueError("Unsupported HTTP status code: %d" % status_code)
    if not _value_re.fullmatch(reason):
        raise ValueError("Invalid HTTP reason phrase: %r" % reason)

    headers = yield from read_headers(stream)

    return status_code, headers


@asyncio.coroutine
def read_headers(stream):
    """
    Read HTTP headers from ``stream``.

    ``stream`` is an :class:`~asyncio.StreamReader`.

    Return a :class:`Headers` instance

    Non-ASCII characters are represented with surrogate escapes.

    """
    # https://tools.ietf.org/html/rfc7230#section-3.2

    # We don't attempt to support obsolete line folding.

    headers = Headers()
    for _ in range(MAX_HEADERS + 1):
        line = yield from read_line(stream)
        if line == b'\r\n':
            break

        # This may raise "ValueError: not enough values to unpack"
        name, value = line[:-2].split(b':', 1)
        if not _token_re.fullmatch(name):
            raise ValueError("Invalid HTTP header name: %r" % name)
        value = value.strip(b' \t')
        if not _value_re.fullmatch(value):
            raise ValueError("Invalid HTTP header value: %r" % value)

        name = name.decode('ascii')  # guaranteed to be ASCII at this point
        value = value.decode('ascii', 'surrogateescape')
        headers[name] = value

    else:
        raise ValueError("Too many HTTP headers")

    return headers


@asyncio.coroutine
def read_line(stream):
    """
    Read a single line from ``stream``.

    ``stream`` is an :class:`~asyncio.StreamReader`.

    """
    # Security: this is bounded by the StreamReader's limit (default = 32kB).
    line = yield from stream.readline()
    # Security: this guarantees header values are small (hard-coded = 4kB)
    if len(line) > MAX_LINE:
        raise ValueError("Line too long")
    # Not mandatory but safe - https://tools.ietf.org/html/rfc7230#section-3.5
    if not line.endswith(b'\r\n'):
        raise ValueError("Line without CRLF")
    return line


class MultipleValuesError(LookupError):
    """
    Exception raised when :class:`Headers` has more than one value for a key.

    """

    def __str__(self):
        # Implement the same logic as KeyError_str in Objects/exceptions.c.
        if len(self.args) == 1:
            return repr(self.args[0])
        return super().__str__()


class Headers(collections.abc.MutableMapping):
    """
    Data structure for working with HTTP headers efficiently.

    A :class:`list` of ``(name, values)`` is inefficient for lookups.

    A :class:`dict` doesn't suffice because header names are case-insensitive
    and multiple occurrences of headers with the same name are possible.

    :class:`Headers` stores HTTP headers in a hybrid data structure to provide
    efficient insertions and lookups while preserving the original data.

    In order to account for multiple values with minimal hassle,
    :class:`Headers` follows this logic:

    - When getting a header with ``headers[name]``:
        - if there's no value, :exc:`KeyError` is raised;
        - if there's exactly one value, it's returned;
        - if there's more than one value, :exc:`MultipleValuesError` is raised.

    - When setting a header with ``headers[name] = value``, the value is
      appended to the list of values for that header.

    - When deleting a header with ``del headers[name]``, all values for that
      header are removed (this is slow).

    Other methods for manipulating headers are consistent with this logic.

    As long as no header occurs multiple times, :class:`Headers` behaves like
    :class:`dict`, except keys are lower-cased to provide case-insensitivity.

    :meth:`get_all()` returns a list of all values for a header and
    :meth:`raw_items()` returns an iterator of ``(name, values)`` pairs,
    similar to :meth:`http.client.HTTPMessage`.

    """

    __slots__ = ['_dict', '_list']

    def __init__(self, *args, **kwargs):
        self._dict = {}
        self._list = []
        # MutableMapping.update calls __setitem__ for each (name, value) pair.
        self.update(*args, **kwargs)

    def __str__(self):
        return (
            ''.join('{}: {}\r\n'.format(key, value) for key, value in self._list)
            + '\r\n'
        )

    def __repr__(self):
        return '{}({})'.format(self.__class__.__name__, repr(self._list))

    def copy(self):
        copy = self.__class__()
        copy._dict = self._dict.copy()
        copy._list = self._list.copy()
        return copy

    # Collection methods

    def __contains__(self, key):
        return key.lower() in self._dict

    def __iter__(self):
        return iter(self._dict)

    def __len__(self):
        return len(self._dict)

    # MutableMapping methods

    def __getitem__(self, key):
        value = self._dict[key.lower()]
        if len(value) == 1:
            return value[0]
        else:
            raise MultipleValuesError(key)

    def __setitem__(self, key, value):
        self._dict.setdefault(key.lower(), []).append(value)
        self._list.append((key, value))

    def __delitem__(self, key):
        key_lower = key.lower()
        self._dict.__delitem__(key_lower)
        # This is inefficent. Fortunately deleting HTTP headers is uncommon.
        self._list = [(k, v) for k, v in self._list if k.lower() != key_lower]

    def __eq__(self, other):
        if not isinstance(other, Headers):
            return NotImplemented
        return self._list == other._list

    def clear(self):
        """
        Remove all headers.

        """
        self._dict = {}
        self._list = []

    # Methods for handling multiple values

    def get_all(self, key):
        """
        Return the (possibly empty) list of all values for a header.

        """
        return self._dict.get(key.lower(), [])

    def raw_items(self):
        """
        Return an iterator of (header name, header value).

        """
        return iter(self._list)
