"""
The :mod:`websockets.client` module defines a simple WebSocket client API.

"""

import asyncio
import collections.abc
import email.message

from .exceptions import InvalidHandshake
from .handshake import build_request, check_response
from .http import USER_AGENT, read_response
from .protocol import CONNECTING, OPEN, WebSocketCommonProtocol
from .uri import parse_uri


__all__ = ['connect', 'WebSocketClientProtocol']


class WebSocketClientProtocol(WebSocketCommonProtocol):
    """
    Complete WebSocket client implementation as an :class:`asyncio.Protocol`.

    This class inherits most of its methods from
    :class:`~websockets.protocol.WebSocketCommonProtocol`.

    """
    is_client = True
    state = CONNECTING

    @asyncio.coroutine
    def handshake(self, wsuri,
                  origin=None, subprotocols=None, extra_headers=None):
        """
        Perform the client side of the opening handshake.

        If provided, ``origin`` sets the Origin HTTP header.

        If provided, ``subprotocols`` is a list of supported subprotocols in
        order of decreasing preference.

        If provided, ``extra_headers`` sets additional HTTP request headers.
        It must be a mapping or an iterable of (name, value) pairs.

        """
        headers = []
        set_header = lambda k, v: headers.append((k, v))
        if wsuri.port == (443 if wsuri.secure else 80):     # pragma: no cover
            set_header('Host', wsuri.host)
        else:
            set_header('Host', '{}:{}'.format(wsuri.host, wsuri.port))
        if origin is not None:
            set_header('Origin', origin)
        if subprotocols is not None:
            set_header('Sec-WebSocket-Protocol', ', '.join(subprotocols))
        if extra_headers is not None:
            if isinstance(extra_headers, collections.abc.Mapping):
                extra_headers = extra_headers.items()
            for name, value in extra_headers:
                set_header(name, value)
        set_header('User-Agent', USER_AGENT)
        key = build_request(set_header)

        self.request_headers = email.message.Message()
        for name, value in headers:
            self.request_headers[name] = value
        self.raw_request_headers = headers

        # Send handshake request. Since the URI and the headers only contain
        # ASCII characters, we can keep this simple.
        request = ['GET %s HTTP/1.1' % wsuri.resource_name]
        request.extend('{}: {}'.format(k, v) for k, v in headers)
        request.append('\r\n')
        request = '\r\n'.join(request).encode()
        self.writer.write(request)

        # Read handshake response.
        try:
            status_code, headers = yield from read_response(self.reader)
        except ValueError as exc:
            raise InvalidHandshake("Malformed HTTP message") from exc
        if status_code != 101:
            raise InvalidHandshake("Bad status code: {}".format(status_code))

        self.response_headers = headers
        self.raw_response_headers = list(headers.raw_items())

        get_header = lambda k: headers.get(k, '')
        check_response(get_header, key)

        self.subprotocol = headers.get('Sec-WebSocket-Protocol', None)
        if (self.subprotocol is not None and
                self.subprotocol not in subprotocols):
            raise InvalidHandshake(
                "Unknown subprotocol: {}".format(self.subprotocol))

        assert self.state == CONNECTING
        self.state = OPEN
        self.opening_handshake.set_result(True)


@asyncio.coroutine
def connect(uri, *,
            klass=WebSocketClientProtocol,
            timeout=10, max_size=2 ** 20, max_queue=2 ** 5,
            loop=None, legacy_recv=False,
            origin=None, subprotocols=None, extra_headers=None,
            **kwds):
    """
    This coroutine connects to a WebSocket server at a given ``uri``.

    It yields a :class:`WebSocketClientProtocol` which can then be used to
    send and receive messages.

    :func:`connect` is a wrapper around the event loop's
    :meth:`~asyncio.BaseEventLoop.create_connection` method. Extra keyword
    arguments are passed to :meth:`~asyncio.BaseEventLoop.create_connection`.

    For example, you can set the ``ssl`` keyword argument to a
    :class:`~ssl.SSLContext` to enforce some TLS settings. When connecting to
    a ``wss://`` URI, if this argument isn't provided explicitly, it's set to
    ``True``, which means Python's default :class:`~ssl.SSLContext` is used.

    The behavior of the ``timeout``, ``max_size``, and ``max_queue`` optional
    arguments is described the documentation of
    :class:`~websockets.protocol.WebSocketCommonProtocol`.

    :func:`connect` also accepts the following optional arguments:

    * ``origin`` sets the Origin HTTP header
    * ``subprotocols`` is a list of supported subprotocols in order of
      decreasing preference
    * ``extra_headers`` sets additional HTTP request headers – it can be a
      mapping or an iterable of (name, value) pairs

    :func:`connect` raises :exc:`~websockets.uri.InvalidURI` if ``uri`` is
    invalid and :exc:`~websockets.handshake.InvalidHandshake` if the opening
    handshake fails.

    On Python 3.5, :func:`connect` can be used as a asynchronous context
    manager. In that case, the connection is closed when exiting the context.

    """
    if loop is None:
        loop = asyncio.get_event_loop()

    wsuri = parse_uri(uri)
    if wsuri.secure:
        kwds.setdefault('ssl', True)
    elif 'ssl' in kwds:
        raise ValueError("connect() received a SSL context for a ws:// URI. "
                         "Use a wss:// URI to enable TLS.")
    factory = lambda: klass(
        host=wsuri.host, port=wsuri.port, secure=wsuri.secure,
        timeout=timeout, max_size=max_size, max_queue=max_queue,
        loop=loop, legacy_recv=legacy_recv,
    )

    transport, protocol = yield from loop.create_connection(
        factory, wsuri.host, wsuri.port, **kwds)

    try:
        yield from protocol.handshake(
            wsuri, origin=origin, subprotocols=subprotocols,
            extra_headers=extra_headers)
    except Exception:
        yield from protocol.close_connection(force=True)
        raise

    return protocol


try:
    from .py35.client import Connect
except (SyntaxError, ImportError):                          # pragma: no cover
    pass
else:
    Connect.__wrapped__ = connect
    # Copy over docstring to support building documentation on Python 3.5.
    Connect.__doc__ = connect.__doc__
    connect = Connect
