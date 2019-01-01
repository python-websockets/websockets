"""
The :mod:`websockets.client` module defines a simple WebSocket client API.

"""

import asyncio
import collections.abc
import logging
import sys

from .exceptions import (
    InvalidHandshake,
    InvalidMessage,
    InvalidStatusCode,
    NegotiationError,
    RedirectHandshake,
)
from .extensions.permessage_deflate import ClientPerMessageDeflateFactory
from .handshake import build_request, check_response
from .headers import (
    build_basic_auth,
    build_extension_list,
    build_subprotocol_list,
    parse_extension_list,
    parse_subprotocol_list,
)
from .http import USER_AGENT, Headers, read_response
from .protocol import WebSocketCommonProtocol
from .uri import parse_uri


__all__ = ["connect", "WebSocketClientProtocol"]

logger = logging.getLogger(__name__)


class WebSocketClientProtocol(WebSocketCommonProtocol):
    """
    Complete WebSocket client implementation as an :class:`asyncio.Protocol`.

    This class inherits most of its methods from
    :class:`~websockets.protocol.WebSocketCommonProtocol`.

    """

    is_client = True
    side = "client"

    def __init__(
        self,
        *,
        origin=None,
        extensions=None,
        subprotocols=None,
        extra_headers=None,
        **kwds
    ):
        self.origin = origin
        self.available_extensions = extensions
        self.available_subprotocols = subprotocols
        self.extra_headers = extra_headers
        super().__init__(**kwds)

    def write_http_request(self, path, headers):
        """
        Write request line and headers to the HTTP request.

        """
        self.path = path
        self.request_headers = headers

        logger.debug("%s > GET %s HTTP/1.1", self.side, path)
        logger.debug("%s > %r", self.side, headers)

        # Since the path and headers only contain ASCII characters,
        # we can keep this simple.
        request = "GET {path} HTTP/1.1\r\n".format(path=path)
        request += str(headers)

        self.writer.write(request.encode())

    async def read_http_response(self):
        """
        Read status line and headers from the HTTP response.

        Raise :exc:`~websockets.exceptions.InvalidMessage` if the HTTP message
        is malformed or isn't an HTTP/1.1 GET request.

        Don't attempt to read the response body because WebSocket handshake
        responses don't have one. If the response contains a body, it may be
        read from ``self.reader`` after this coroutine returns.

        """
        try:
            status_code, reason, headers = await read_response(self.reader)
        except ValueError as exc:
            raise InvalidMessage("Malformed HTTP message") from exc

        logger.debug("%s < HTTP/1.1 %d %s", self.side, status_code, reason)
        logger.debug("%s < %r", self.side, headers)

        self.response_headers = headers

        return status_code, self.response_headers

    @staticmethod
    def process_extensions(headers, available_extensions):
        """
        Handle the Sec-WebSocket-Extensions HTTP response header.

        Check that each extension is supported, as well as its parameters.

        Return the list of accepted extensions.

        Raise :exc:`~websockets.exceptions.InvalidHandshake` to abort the
        connection.

        :rfc:`6455` leaves the rules up to the specification of each
        :extension.

        To provide this level of flexibility, for each extension accepted by
        the server, we check for a match with each extension available in the
        client configuration. If no match is found, an exception is raised.

        If several variants of the same extension are accepted by the server,
        it may be configured severel times, which won't make sense in general.
        Extensions must implement their own requirements. For this purpose,
        the list of previously accepted extensions is provided.

        Other requirements, for example related to mandatory extensions or the
        order of extensions, may be implemented by overriding this method.

        """
        accepted_extensions = []

        header_values = headers.get_all("Sec-WebSocket-Extensions")

        if header_values:

            if available_extensions is None:
                raise InvalidHandshake("No extensions supported")

            parsed_header_values = sum(
                [parse_extension_list(header_value) for header_value in header_values],
                [],
            )

            for name, response_params in parsed_header_values:

                for extension_factory in available_extensions:

                    # Skip non-matching extensions based on their name.
                    if extension_factory.name != name:
                        continue

                    # Skip non-matching extensions based on their params.
                    try:
                        extension = extension_factory.process_response_params(
                            response_params, accepted_extensions
                        )
                    except NegotiationError:
                        continue

                    # Add matching extension to the final list.
                    accepted_extensions.append(extension)

                    # Break out of the loop once we have a match.
                    break

                # If we didn't break from the loop, no extension in our list
                # matched what the server sent. Fail the connection.
                else:
                    raise NegotiationError(
                        "Unsupported extension: name = {}, params = {}".format(
                            name, response_params
                        )
                    )

        return accepted_extensions

    @staticmethod
    def process_subprotocol(headers, available_subprotocols):
        """
        Handle the Sec-WebSocket-Protocol HTTP response header.

        Check that it contains exactly one supported subprotocol.

        Return the selected subprotocol.

        """
        subprotocol = None

        header_values = headers.get_all("Sec-WebSocket-Protocol")

        if header_values:

            if available_subprotocols is None:
                raise InvalidHandshake("No subprotocols supported")

            parsed_header_values = sum(
                [
                    parse_subprotocol_list(header_value)
                    for header_value in header_values
                ],
                [],
            )

            if len(parsed_header_values) > 1:
                raise InvalidHandshake(
                    "Multiple subprotocols: {}".format(", ".join(parsed_header_values))
                )

            subprotocol = parsed_header_values[0]

            if subprotocol not in available_subprotocols:
                raise NegotiationError(
                    "Unsupported subprotocol: {}".format(subprotocol)
                )

        return subprotocol

    async def handshake(
        self,
        wsuri,
        origin=None,
        available_extensions=None,
        available_subprotocols=None,
        extra_headers=None,
    ):
        """
        Perform the client side of the opening handshake.

        If provided, ``origin`` sets the Origin HTTP header.

        If provided, ``available_extensions`` is a list of supported
        extensions in the order in which they should be used.

        If provided, ``available_subprotocols`` is a list of supported
        subprotocols in order of decreasing preference.

        If provided, ``extra_headers`` sets additional HTTP request headers.
        It must be a :class:`~websockets.http.Headers` instance, a
        :class:`~collections.abc.Mapping`, or an iterable of ``(name, value)``
        pairs.

        Raise :exc:`~websockets.exceptions.InvalidHandshake` if the handshake
        fails.

        """
        request_headers = Headers()

        if wsuri.port == (443 if wsuri.secure else 80):  # pragma: no cover
            request_headers["Host"] = wsuri.host
        else:
            request_headers["Host"] = "{}:{}".format(wsuri.host, wsuri.port)

        if wsuri.user_info:
            request_headers["Authorization"] = build_basic_auth(*wsuri.user_info)

        if origin is not None:
            request_headers["Origin"] = origin

        key = build_request(request_headers)

        if available_extensions is not None:
            extensions_header = build_extension_list(
                [
                    (extension_factory.name, extension_factory.get_request_params())
                    for extension_factory in available_extensions
                ]
            )
            request_headers["Sec-WebSocket-Extensions"] = extensions_header

        if available_subprotocols is not None:
            protocol_header = build_subprotocol_list(available_subprotocols)
            request_headers["Sec-WebSocket-Protocol"] = protocol_header

        if extra_headers is not None:
            if isinstance(extra_headers, Headers):
                extra_headers = extra_headers.raw_items()
            elif isinstance(extra_headers, collections.abc.Mapping):
                extra_headers = extra_headers.items()
            for name, value in extra_headers:
                request_headers[name] = value

        request_headers.setdefault("User-Agent", USER_AGENT)

        self.write_http_request(wsuri.resource_name, request_headers)

        status_code, response_headers = await self.read_http_response()
        if status_code in (301, 302, 303, 307, 308):
            if "Location" not in response_headers:
                raise InvalidMessage("Redirect response missing Location")
            raise RedirectHandshake(parse_uri(response_headers["Location"]))
        elif status_code != 101:
            raise InvalidStatusCode(status_code)

        check_response(response_headers, key)

        self.extensions = self.process_extensions(
            response_headers, available_extensions
        )

        self.subprotocol = self.process_subprotocol(
            response_headers, available_subprotocols
        )

        self.connection_open()


class Connect:
    """
    Connect to the WebSocket server at the given ``uri``.

    :func:`connect` returns an awaitable. Awaiting it yields an instance of
    :class:`WebSocketClientProtocol` which can then be used to send and
    receive messages.

    On Python ≥ 3.5.1, :func:`connect` can be used as a asynchronous context
    manager. In that case, the connection is closed when exiting the context.

    :func:`connect` is a wrapper around the event loop's
    :meth:`~asyncio.BaseEventLoop.create_connection` method. Unknown keyword
    arguments are passed to :meth:`~asyncio.BaseEventLoop.create_connection`.

    For example, you can set the ``ssl`` keyword argument to a
    :class:`~ssl.SSLContext` to enforce some TLS settings. When connecting to
    a ``wss://`` URI, if this argument isn't provided explicitly, it's set to
    ``True``, which means Python's default :class:`~ssl.SSLContext` is used.

    Normally ``host`` and ``port`` parameters of
    :meth:`~asyncio.BaseEventLoop.create_connection` are populated from the
    supplied URI, but can be overwritten by the caller if desired, this can be
    useful when connecting via ssh tunnel for example.

    The behavior of the ``ping_interval``, ``ping_timeout``, ``close_timeout``,
    ``max_size``, ``max_queue``, ``read_limit``, and ``write_limit`` optional
    arguments is described in the documentation of
    :class:`~websockets.protocol.WebSocketCommonProtocol`.

    The ``create_protocol`` parameter allows customizing the asyncio protocol
    that manages the connection. It should be a callable or class accepting
    the same arguments as :class:`WebSocketClientProtocol` and returning a
    :class:`WebSocketClientProtocol` instance. It defaults to
    :class:`WebSocketClientProtocol`.

    :func:`connect` also accepts the following optional arguments:

    * ``compression`` is a shortcut to configure compression extensions;
      by default it enables the "permessage-deflate" extension; set it to
      ``None`` to disable compression
    * ``origin`` sets the Origin HTTP header
    * ``extensions`` is a list of supported extensions in order of
      decreasing preference
    * ``subprotocols`` is a list of supported subprotocols in order of
      decreasing preference
    * ``extra_headers`` sets additional HTTP request headers – it can be a
      :class:`~websockets.http.Headers` instance, a
      :class:`~collections.abc.Mapping`, or an iterable of ``(name, value)``
      pairs

    :func:`connect` raises :exc:`~websockets.uri.InvalidURI` if ``uri`` is
    invalid and :exc:`~websockets.handshake.InvalidHandshake` if the opening
    handshake fails.

    """

    MAX_REDIRECTS_ALLOWED = 10

    def __init__(
        self,
        uri,
        *,
        create_protocol=None,
        ping_interval=20,
        ping_timeout=20,
        close_timeout=None,
        max_size=2 ** 20,
        max_queue=2 ** 5,
        read_limit=2 ** 16,
        write_limit=2 ** 16,
        loop=None,
        legacy_recv=False,
        klass=WebSocketClientProtocol,
        timeout=10,
        compression="deflate",
        origin=None,
        extensions=None,
        subprotocols=None,
        extra_headers=None,
        **kwds
    ):
        if loop is None:
            loop = asyncio.get_event_loop()

        # Backwards-compatibility: close_timeout used to be called timeout.
        # If both are specified, timeout is ignored.
        if close_timeout is None:
            close_timeout = timeout

        # Backwards-compatibility: create_protocol used to be called klass.
        # If both are specified, klass is ignored.
        if create_protocol is None:
            create_protocol = klass

        self._wsuri = parse_uri(uri)
        if self._wsuri.secure:
            kwds.setdefault("ssl", True)
        elif kwds.get("ssl") is not None:
            raise ValueError(
                "connect() received a SSL context for a ws:// URI, "
                "use a wss:// URI to enable TLS"
            )

        if compression == "deflate":
            if extensions is None:
                extensions = []
            if not any(
                extension_factory.name == ClientPerMessageDeflateFactory.name
                for extension_factory in extensions
            ):
                extensions.append(
                    ClientPerMessageDeflateFactory(client_max_window_bits=True)
                )
        elif compression is not None:
            raise ValueError("Unsupported compression: {}".format(compression))

        self._create_protocol = create_protocol
        self._ping_interval = ping_interval
        self._ping_timeout = ping_timeout
        self._close_timeout = close_timeout
        self._max_size = max_size
        self._max_queue = max_queue
        self._read_limit = read_limit
        self._write_limit = write_limit
        self._loop = loop
        self._legacy_recv = legacy_recv
        self._klass = klass
        self._timeout = timeout
        self._compression = compression
        self._origin = origin
        self._extensions = extensions
        self._subprotocols = subprotocols
        self._extra_headers = extra_headers
        self._kwds = kwds

    def _creating_connection(self):
        if self._wsuri.secure:
            self._kwds.setdefault("ssl", True)

        factory = lambda: self._create_protocol(
            host=self._wsuri.host,
            port=self._wsuri.port,
            secure=self._wsuri.secure,
            ping_interval=self._ping_interval,
            ping_timeout=self._ping_timeout,
            close_timeout=self._close_timeout,
            max_size=self._max_size,
            max_queue=self._max_queue,
            read_limit=self._read_limit,
            write_limit=self._write_limit,
            loop=self._loop,
            legacy_recv=self._legacy_recv,
            origin=self._origin,
            extensions=self._extensions,
            subprotocols=self._subprotocols,
            extra_headers=self._extra_headers,
        )
        kwds = self._kwds.copy()

        if kwds.get("sock") is None:
            kwds.setdefault("host", self._wsuri.host)
            kwds.setdefault("port", self._wsuri.port)

        if kwds.get("ssl") and kwds.get("host") != self._wsuri.host:
            kwds.setdefault("server_hostname", self._wsuri.host)

        self._wsuri = self._wsuri
        self._origin = self._origin

        # This is a coroutine object.
        return self._loop.create_connection(factory, **kwds)

    @asyncio.coroutine
    def __iter__(self):
        return self.__await_impl__()

    async def __aenter__(self):
        return await self

    async def __aexit__(self, exc_type, exc_value, traceback):
        await self.ws_client.close()

    async def __await_impl__(self):
        for redirects in range(self.MAX_REDIRECTS_ALLOWED):
            transport, protocol = await self._creating_connection()

            try:
                try:
                    await protocol.handshake(
                        self._wsuri,
                        origin=self._origin,
                        available_extensions=protocol.available_extensions,
                        available_subprotocols=protocol.available_subprotocols,
                        extra_headers=protocol.extra_headers,
                    )
                    break  # redirection chain ended
                except Exception:
                    protocol.fail_connection()
                    await protocol.wait_closed()
                    raise
            except RedirectHandshake as e:
                if self._wsuri.secure and not e.wsuri.secure:
                    raise InvalidHandshake("Redirect dropped TLS")
                self._wsuri = e.wsuri
                continue  # redirection chain continues
        else:
            raise InvalidHandshake("Maximum redirects exceeded")

        self.ws_client = protocol
        return protocol

    def __await__(self):
        # __await__() must return a type that I don't know how to obtain except
        # by calling __await__() on the return value of an async function.
        # I'm not finding a better way to take advantage of PEP 492.
        return self.__await_impl__().__await__()


# We can't define __await__ on Python < 3.5.1 because asyncio.ensure_future
# didn't accept arbitrary awaitables until Python 3.5.1. We don't define
# __aenter__ and __aexit__ either on Python < 3.5.1 to keep things simple.
if sys.version_info[:3] < (3, 5, 1):  # pragma: no cover

    del Connect.__aenter__
    del Connect.__aexit__
    del Connect.__await__

    async def connect(*args, **kwds):
        return Connect(*args, **kwds).__iter__()

    connect.__doc__ = Connect.__doc__

else:

    connect = Connect
