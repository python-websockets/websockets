from __future__ import annotations

import logging
import os
import socket
import ssl as ssl_module
import threading
import time
import traceback
import urllib.parse
import warnings
from collections.abc import Generator, Iterator, Sequence
from types import TracebackType
from typing import Any, Callable, Literal, TypeVar, cast, overload

from ..client import ClientProtocol, backoff, process_exception
from ..datastructures import Headers, HeadersLike
from ..exceptions import (
    InvalidProxyMessage,
    InvalidProxyStatus,
    InvalidStatus,
    ProxyError,
    SecurityError,
)
from ..extensions.base import ClientExtensionFactory
from ..extensions.permessage_deflate import enable_client_permessage_deflate
from ..headers import validate_subprotocols
from ..http11 import USER_AGENT, Response
from ..protocol import CONNECTING, Event
from ..proxy import Proxy, get_proxy, parse_proxy, prepare_connect_request
from ..streams import StreamReader
from ..typing import BytesLike, LoggerLike, Origin, PathLike, Subprotocol
from ..uri import WebSocketURI, parse_uri
from .connection import Connection
from .utils import Deadline


__all__ = ["connect", "unix_connect", "reconnect", "unix_reconnect", "ClientConnection"]

MAX_REDIRECTS = int(os.environ.get("WEBSOCKETS_MAX_REDIRECTS", "10"))


class ClientConnection(Connection):
    """
    :mod:`threading` implementation of a WebSocket client connection.

    :class:`ClientConnection` provides :meth:`recv` and :meth:`send` methods for
    receiving and sending messages.

    It supports iteration to receive messages::

        for message in websocket:
            process(message)

    The iterator exits normally when the connection is closed with code
    1000 (OK) or 1001 (going away) or without a close code. It raises a
    :exc:`~websockets.exceptions.ConnectionClosedError` when the connection is
    closed with any other code.

    The ``ping_interval``, ``ping_timeout``, ``close_timeout``, and
    ``max_queue`` arguments have the same meaning as in :func:`connect`.

    Args:
        socket: Socket connected to a WebSocket server.
        protocol: Sans-I/O connection.

    """

    def __init__(
        self,
        sock: socket.socket,
        protocol: ClientProtocol,
        *,
        ping_interval: float | None = 20,
        ping_timeout: float | None = 20,
        close_timeout: float | None = 10,
        max_queue: int | None | tuple[int | None, int | None] = 16,
    ) -> None:
        self.protocol: ClientProtocol
        self.response_rcvd = threading.Event()
        self.pending_legacy_warning = True
        super().__init__(
            sock,
            protocol,
            ping_interval=ping_interval,
            ping_timeout=ping_timeout,
            close_timeout=close_timeout,
            max_queue=max_queue,
        )

    def __enter__(self) -> ClientConnection:
        self.pending_legacy_warning = False
        return super().__enter__()

    def maybe_raise_legacy_warning(self) -> None:
        if self.pending_legacy_warning:
            self.pending_legacy_warning = False
            warnings.warn(  # deprecated in 17.1
                "connect() must be used as a context manager: "
                "with connect(...) as websocket: ...; alternatively, use "
                "websocket = connect(..., legacy=True) to connect directly",
                DeprecationWarning,
                stacklevel=3,
            )

    def handshake(
        self,
        additional_headers: HeadersLike | None = None,
        user_agent_header: str | None = USER_AGENT,
        timeout: float | None = None,
    ) -> None:
        """
        Perform the opening handshake.

        """
        self.request = self.protocol.connect()
        if additional_headers is not None:
            self.request.headers.update(additional_headers)
        if user_agent_header is not None:
            self.request.headers.setdefault("User-Agent", user_agent_header)
        with self.send_context(expected_state=CONNECTING):
            self.protocol.send_request(self.request)

        if not self.response_rcvd.wait(timeout):
            raise TimeoutError("timed out while waiting for handshake response")

        # self.protocol.handshake_exc is set when the connection is lost before
        # receiving a response, when the response cannot be parsed, or when the
        # response fails the handshake.

        if self.protocol.handshake_exc is not None:
            raise self.protocol.handshake_exc

    def process_event(self, event: Event) -> None:
        """
        Process one incoming event.

        """
        # First event - handshake response.
        if self.response is None:
            assert isinstance(event, Response)
            self.response = event
            self.response_rcvd.set()
        # Later events - frames.
        else:
            super().process_event(event)

    def recv_events(self) -> None:
        """
        Read incoming data from the socket and process events.

        """
        try:
            super().recv_events()
        finally:
            # If the connection is closed during the handshake, unblock it.
            self.response_rcvd.set()


class reconnect:
    """
    Similar to :func:`connect`, with support for automatic reconnection.

    :func:`reconnect` can also be treated as an infinite iterator to reconnect
    automatically on errors::

        for websocket in reconnect(...):
            try:
                ...
            except websockets.exceptions.ConnectionClosed:
                continue

    If the connection fails with a transient error, it is retried with
    exponential backoff. If it fails with a fatal error, the exception is
    raised, breaking out of the loop.

    The connection is closed automatically after each iteration of the loop.

    :func:`reconnect` accepts the same arguments as :func:`connect`, minus the
    ``legacy`` flag, plus those listed below. It raises the same exceptions.

    Args:
        process_exception: When reconnecting automatically, tell whether an
            error is transient or fatal. The default behavior is defined by
            :func:`~websockets.client.process_exception`. Refer to its
            documentation for details.
        reconnect_delays: Delays in seconds between reconnection attempts.
            Default is exponential backoff with 5s jitter, capped at 60s.

    .. admonition:: Why is :func:`reconnect` a separate API from :func:`connect`?
        :class: tip

        A new API was necessary to maintain backwards compatibility with this
        historical behavior of :func:`connect`::

            websocket = connect(...)
            for message in websocket:
                ...

        Once the deprecation period elapses, :func:`connect` will be changed to
        behave like :func:`reconnect` by default.

    """

    def __init__(
        self,
        uri: str,
        *,
        # TCP/TLS
        sock: socket.socket | None = None,
        ssl: ssl_module.SSLContext | None = None,
        server_hostname: str | None = None,
        # WebSocket
        origin: Origin | None = None,
        extensions: Sequence[ClientExtensionFactory] | None = None,
        subprotocols: Sequence[Subprotocol] | None = None,
        compression: str | None = "deflate",
        # HTTP
        additional_headers: HeadersLike | None = None,
        user_agent_header: str | None = USER_AGENT,
        proxy: str | Literal[True] | None = True,
        proxy_ssl: ssl_module.SSLContext | None = None,
        proxy_server_hostname: str | None = None,
        process_exception: Callable[[Exception], Exception | None] = process_exception,
        # Timeouts
        open_timeout: float | None = 10,
        ping_interval: float | None = 20,
        ping_timeout: float | None = 20,
        close_timeout: float | None = 10,
        reconnect_delays: Callable[[], Generator[float]] = backoff,
        # Limits
        max_size: int | None | tuple[int | None, int | None] = 2**20,
        max_queue: int | None | tuple[int | None, int | None] = 16,
        # Logging
        logger: LoggerLike | None = None,
        # Escape hatch for advanced customization
        create_connection: type[ClientConnection] | None = None,
        # Other keyword arguments are passed to socket.create_connection
        **kwargs: Any,
    ) -> None:
        # Backwards compatibility: ssl used to be called ssl_context.
        if ssl is None and "ssl_context" in kwargs:
            ssl = kwargs.pop("ssl_context")
            warnings.warn(  # deprecated in 13.0 - 2024-08-20
                "ssl_context was renamed to ssl",
                DeprecationWarning,
            )

        self.uri = uri
        self.ws_uri = parse_uri(uri)
        if not self.ws_uri.secure and ssl is not None:
            raise ValueError("ssl argument is incompatible with a ws:// URI")

        if subprotocols is not None:
            validate_subprotocols(subprotocols)

        if compression == "deflate":
            extensions = enable_client_permessage_deflate(extensions)
        elif compression is not None:
            raise ValueError(f"unsupported compression: {compression}")

        if logger is None:
            logger = logging.getLogger("websockets.client")

        if create_connection is None:
            create_connection = ClientConnection

        self.sock = sock
        self.ssl = ssl
        self.server_hostname = server_hostname
        self.additional_headers = additional_headers
        self.user_agent_header = user_agent_header
        self.proxy = proxy
        self.proxy_ssl = proxy_ssl
        self.proxy_server_hostname = proxy_server_hostname
        self.process_exception = process_exception
        self.open_timeout = open_timeout
        self.reconnect_delays = reconnect_delays
        self.logger = logger
        self.create_connection = create_connection
        self.open_socket_kwargs = kwargs
        self.protocol_kwargs = dict(
            origin=origin,
            extensions=extensions,
            subprotocols=subprotocols,
            max_size=max_size,
            logger=logger,
        )
        self.connection_kwargs = dict(
            ping_interval=ping_interval,
            ping_timeout=ping_timeout,
            close_timeout=close_timeout,
            max_queue=max_queue,
        )

    def open_socket(self, deadline: Deadline) -> socket.socket:
        """Open a TCP or Unix connection to the server, possibly through a proxy."""
        kwargs = self.open_socket_kwargs.copy()
        unix = kwargs.pop("unix", False)

        proxy = self.proxy
        if unix:
            proxy = None
        if proxy is True:
            proxy = get_proxy(self.ws_uri)

        if unix:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                sock.settimeout(deadline.timeout())
                sock.connect(os.fspath(kwargs.pop("path")))
            except Exception:
                sock.close()
                raise

        elif proxy is not None:
            proxy_parsed = parse_proxy(proxy)

            if proxy_parsed.scheme[:5] == "socks":
                sock = connect_socks_proxy(
                    proxy_parsed,
                    self.ws_uri,
                    deadline,
                    # websockets is consistent with the socket module while
                    # python_socks is consistent across implementations.
                    local_addr=kwargs.pop("source_address", None),
                )

            elif proxy_parsed.scheme[:4] == "http":
                if proxy_parsed.scheme != "https" and self.proxy_ssl is not None:
                    raise ValueError(
                        "proxy_ssl argument is incompatible with an http:// proxy"
                    )
                sock = connect_http_proxy(
                    proxy_parsed,
                    self.ws_uri,
                    deadline,
                    user_agent_header=self.user_agent_header,
                    ssl=self.proxy_ssl,
                    server_hostname=self.proxy_server_hostname,
                    **kwargs,
                )

            else:
                raise AssertionError("parse_proxy returned unsupported proxy")

        else:  # proxy is None
            kwargs.setdefault("address", (self.ws_uri.host, self.ws_uri.port))
            kwargs.setdefault("timeout", deadline.timeout())
            sock = socket.create_connection(**kwargs)

        sock.settimeout(None)
        return sock

    def enable_tls(self, sock: socket.socket, deadline: Deadline) -> socket.socket:
        """Enable TLS on the connection."""
        if self.ssl is None:
            ssl = ssl_module.create_default_context()
        else:
            ssl = self.ssl
        if self.server_hostname is None:
            server_hostname = self.ws_uri.host
        else:
            server_hostname = self.server_hostname
        sock.settimeout(deadline.timeout())
        if self.proxy_ssl is None:
            sock = ssl.wrap_socket(sock, server_hostname=server_hostname)
        else:
            sock_2 = SSLSSLSocket(sock, ssl, server_hostname=server_hostname)
            # Let's pretend that sock is a socket, even though it isn't.
            sock = cast(socket.socket, sock_2)
        sock.settimeout(None)
        return sock

    def open_connection(self, deadline: Deadline) -> ClientConnection:
        """Create a WebSocket connection."""
        if self.sock is None:
            sock = self.open_socket(deadline)
        else:
            sock = self.sock

        try:
            if sock.family in {socket.AF_INET, socket.AF_INET6}:
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, True)

            if self.ws_uri.secure:
                sock = self.enable_tls(sock, deadline)

            protocol = ClientProtocol(
                self.ws_uri,
                **self.protocol_kwargs,  # type: ignore
            )

            # self.create_connection defaults to ClientConnection.
            connection = self.create_connection(
                sock,
                protocol,
                **self.connection_kwargs,  # type: ignore
            )

        except Exception:
            sock.close()
            raise

        try:
            connection.handshake(
                self.additional_headers,
                self.user_agent_header,
                deadline.timeout(),
            )
        except Exception:
            connection.close_socket()
            connection.recv_events_thread.join()
            raise

        return connection

    def process_redirect(self, exc: Exception) -> Exception | str:
        """
        Determine whether a connection error is a redirect that can be followed.

        Return the new URI if it's a valid redirect. Else, return an exception.

        """
        if not (
            isinstance(exc, InvalidStatus)
            and exc.response.status_code
            in [
                300,  # Multiple Choices
                301,  # Moved Permanently
                302,  # Found
                303,  # See Other
                307,  # Temporary Redirect
                308,  # Permanent Redirect
            ]
            and "Location" in exc.response.headers
        ):
            return exc

        old_ws_uri = self.ws_uri
        new_uri = urllib.parse.urljoin(self.uri, exc.response.headers["Location"])
        new_ws_uri = parse_uri(new_uri)

        # If connect() received a socket, it is closed and cannot be reused.
        if self.sock is not None:
            return ValueError(
                f"cannot follow redirect to {new_uri} with a preexisting socket"
            )

        # TLS downgrade is forbidden.
        if old_ws_uri.secure and not new_ws_uri.secure:
            return SecurityError(f"cannot follow redirect to non-secure URI {new_uri}")

        # Apply restrictions to cross-origin redirects.
        if (
            old_ws_uri.secure != new_ws_uri.secure
            or old_ws_uri.host != new_ws_uri.host
            or old_ws_uri.port != new_ws_uri.port
        ):
            # Cross-origin redirects on Unix sockets don't quite make sense.
            if self.open_socket_kwargs.get("unix", False):
                return ValueError(
                    f"cannot follow cross-origin redirect to {new_uri} "
                    f"with a Unix socket"
                )

            # Cross-origin redirects when host and port are overridden are ill-defined.
            if self.open_socket_kwargs.get("address") is not None:
                return ValueError(
                    f"cannot follow cross-origin redirect to {new_uri} "
                    f"with an explicit host and port"
                )

            # Strip credentials to avoid leaking them to a different origin.
            if self.additional_headers is not None:
                self.additional_headers = Headers(
                    (
                        (key, value)
                        for key, value in Headers(self.additional_headers).raw_items()
                        if key.lower()
                        not in ["authorization", "cookie", "proxy-authorization"]
                    )
                )

        return new_uri

    def connect(self) -> ClientConnection:
        """Connect to a WebSocket server, following redirects."""
        # Calculate timeouts on the TCP, TLS, and WebSocket handshakes.
        # The TCP and TLS timeouts must be set on the socket, then removed
        # to avoid conflicting with the WebSocket timeout in handshake().
        deadline = Deadline(self.open_timeout)

        for _ in range(MAX_REDIRECTS):
            try:
                connection = self.open_connection(deadline)
            except Exception as exc:
                exc_or_uri = self.process_redirect(exc)
                if isinstance(exc_or_uri, Exception):
                    # Response isn't a valid redirect; raise the exception.
                    if exc_or_uri is exc:
                        raise
                    else:
                        raise exc_or_uri from exc
                else:
                    # Response is a valid redirect; follow it.
                    self.uri = exc_or_uri
                    self.ws_uri = parse_uri(exc_or_uri)
                    continue

            else:
                connection.start_keepalive()
                return connection
        else:
            raise SecurityError(f"more than {MAX_REDIRECTS} redirects")

    # with connect(...) as ...: ...

    def __enter__(self) -> ClientConnection:
        if hasattr(self, "connection"):
            raise RuntimeError("connect() isn't reentrant")
        self.connection = self.connect()
        self.connection.pending_legacy_warning = False
        return self.connection

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        exc_traceback: TracebackType | None,
    ) -> None:
        try:
            self.connection.close()
        finally:
            del self.connection

    # for ... in reconnect(...): ...

    def __iter__(self) -> Iterator[ClientConnection]:
        delays: Generator[float] | None = None
        while True:
            try:
                with self as connection:
                    yield connection
            except Exception as exc:
                # Determine whether the exception is retryable or fatal.
                # The API of process_exception is "return an exception or None";
                # "raise an exception" is also supported because it's a frequent
                # mistake. It isn't documented in order to keep the API simple.
                try:
                    new_exc = self.process_exception(exc)
                except Exception as raised_exc:
                    new_exc = raised_exc

                # The connection failed with a fatal error.
                # Raise the exception and exit the loop.
                if new_exc is exc:
                    raise
                if new_exc is not None:
                    raise new_exc from exc

                # The connection failed with a retryable error.
                # Start or continue backoff and reconnect.
                if delays is None:
                    delays = self.reconnect_delays()
                delay = next(delays)
                self.logger.info(
                    "connect failed; reconnecting in %.1f seconds: %s",
                    delay,
                    traceback.format_exception_only(exc)[0].strip(),
                )
                time.sleep(delay)

            else:
                # The connection succeeded. Reset backoff.
                delays = None


@overload
def connect(
    uri: str,
    *,
    # TCP/TLS
    sock: socket.socket | None = ...,
    ssl: ssl_module.SSLContext | None = ...,
    server_hostname: str | None = ...,
    # WebSocket
    origin: Origin | None = ...,
    extensions: Sequence[ClientExtensionFactory] | None = ...,
    subprotocols: Sequence[Subprotocol] | None = ...,
    compression: str | None = ...,
    # HTTP
    additional_headers: HeadersLike | None = ...,
    user_agent_header: str | None = ...,
    proxy: str | Literal[True] | None = ...,
    proxy_ssl: ssl_module.SSLContext | None = ...,
    proxy_server_hostname: str | None = ...,
    # Timeouts
    open_timeout: float | None = ...,
    ping_interval: float | None = ...,
    ping_timeout: float | None = ...,
    close_timeout: float | None = ...,
    # Limits
    max_size: int | None | tuple[int | None, int | None] = ...,
    max_queue: int | None | tuple[int | None, int | None] = ...,
    # Logging
    logger: LoggerLike | None = ...,
    # Escape hatch for advanced customization
    create_connection: type[ClientConnection] | None = ...,
    # Backwards and forwards compatibility
    legacy: Literal[True] | None = ...,
    # Other keyword arguments are passed to socket.create_connection
    **kwargs: Any,
) -> ClientConnection: ...


@overload
def connect(
    uri: str,
    *,
    # TCP/TLS
    sock: socket.socket | None = ...,
    ssl: ssl_module.SSLContext | None = ...,
    server_hostname: str | None = ...,
    # WebSocket
    origin: Origin | None = ...,
    extensions: Sequence[ClientExtensionFactory] | None = ...,
    subprotocols: Sequence[Subprotocol] | None = ...,
    compression: str | None = ...,
    # HTTP
    additional_headers: HeadersLike | None = ...,
    user_agent_header: str | None = ...,
    proxy: str | Literal[True] | None = ...,
    proxy_ssl: ssl_module.SSLContext | None = ...,
    proxy_server_hostname: str | None = ...,
    # Timeouts
    open_timeout: float | None = ...,
    ping_interval: float | None = ...,
    ping_timeout: float | None = ...,
    close_timeout: float | None = ...,
    # Limits
    max_size: int | None | tuple[int | None, int | None] = ...,
    max_queue: int | None | tuple[int | None, int | None] = ...,
    # Logging
    logger: LoggerLike | None = ...,
    # Escape hatch for advanced customization
    create_connection: type[ClientConnection] | None = ...,
    # Backwards and forwards compatibility
    legacy: Literal[False],
    # Other keyword arguments are passed to socket.create_connection
    **kwargs: Any,
) -> reconnect: ...


def connect(
    uri: str,
    *,
    # TCP/TLS
    sock: socket.socket | None = None,
    ssl: ssl_module.SSLContext | None = None,
    server_hostname: str | None = None,
    # WebSocket
    origin: Origin | None = None,
    extensions: Sequence[ClientExtensionFactory] | None = None,
    subprotocols: Sequence[Subprotocol] | None = None,
    compression: str | None = "deflate",
    # HTTP
    additional_headers: HeadersLike | None = None,
    user_agent_header: str | None = USER_AGENT,
    proxy: str | Literal[True] | None = True,
    proxy_ssl: ssl_module.SSLContext | None = None,
    proxy_server_hostname: str | None = None,
    # Timeouts
    open_timeout: float | None = 10,
    ping_interval: float | None = 20,
    ping_timeout: float | None = 20,
    close_timeout: float | None = 10,
    # Limits
    max_size: int | None | tuple[int | None, int | None] = 2**20,
    max_queue: int | None | tuple[int | None, int | None] = 16,
    # Logging
    logger: LoggerLike | None = None,
    # Escape hatch for advanced customization
    create_connection: type[ClientConnection] | None = None,
    # Backwards and forwards compatibility
    legacy: bool | None = None,
    # Other keyword arguments are passed to socket.create_connection
    **kwargs: Any,
) -> ClientConnection | reconnect:
    """
    Connect to the WebSocket server at ``uri``.

    :func:`connect` should be treated as a context manager yielding a
    :class:`ClientConnection`, which can then receive and send messages::

        from websockets.sync.client import connect

        with connect(...) as websocket:
            ...

    The connection is closed automatically when exiting the context.

    Use :func:`reconnect` to reconnect automatically on errors.

    For backwards compatibility, :func:`connect` can be called directly::

        websocket = connect(..., legacy=True)

    In that case, you're responsible for closing the connection with
    :meth:`ClientConnection.close` when no longer needed.

    When the ``legacy`` flag is enabled, :func:`connect` returns directly a
    :class:`ClientConnection` and iterating that connection yields messages.
    Currently, this is the default behavior when ``legacy`` isn't specified.

    When the ``legacy`` flag is explicitly disabled, :func:`connect` behaves
    like :func:`reconnect`: using it as an iterator returns a new connection
    at each iteration, making it easy to reconnect automatically on errors.

    Args:
        uri: URI of the WebSocket server.
        sock: Preexisting TCP socket. ``sock`` overrides the host and port
            from ``uri``. You may call :func:`socket.create_connection` to
            create a suitable TCP socket.
        ssl: Configuration for enabling TLS on the connection.
        server_hostname: Host name for the TLS handshake. ``server_hostname``
            overrides the host name from ``uri``.
        origin: Value of the ``Origin`` header, for servers that require it.
        extensions: List of supported extensions, in order in which they
            should be negotiated and run.
        subprotocols: List of supported subprotocols, in order of decreasing
            preference.
        compression: The "permessage-deflate" extension is enabled by default.
            Set ``compression`` to :obj:`None` to disable it. See the
            :doc:`compression guide <../../topics/compression>` for details.
        additional_headers: Arbitrary HTTP headers to add to the handshake
            request.
        user_agent_header: Value of  the ``User-Agent`` request header.
            It defaults to ``"Python/x.y.z websockets/X.Y"``.
            Setting it to :obj:`None` removes the header.
        proxy: If a proxy is configured, it is used by default. Set ``proxy``
            to :obj:`None` to disable the proxy or to the address of a proxy
            to override the system configuration. See the :doc:`proxy docs
            <../../topics/proxies>` for details.
        proxy_ssl: Configuration for enabling TLS on the proxy connection.
        proxy_server_hostname: Host name for the TLS handshake with the proxy.
            ``proxy_server_hostname`` overrides the host name from ``proxy``.
        open_timeout: Timeout for opening the connection in seconds.
            :obj:`None` disables the timeout.
        ping_interval: Interval between keepalive pings in seconds.
            :obj:`None` disables keepalive.
        ping_timeout: Timeout for keepalive pings in seconds.
            :obj:`None` disables timeouts.
        close_timeout: Timeout for closing the connection in seconds.
            :obj:`None` disables the timeout.
        max_size: Maximum size of incoming messages in bytes.
            :obj:`None` disables the limit. You may pass a ``(max_message_size,
            max_fragment_size)`` tuple to set different limits for messages and
            fragments when you expect long messages sent in short fragments.
        max_queue: High-water mark of the buffer where frames are received.
            It defaults to 16 frames. The low-water mark defaults to ``max_queue
            // 4``. You may pass a ``(high, low)`` tuple to set the high-water
            and low-water marks. If you want to disable flow control entirely,
            you may set it to ``None``, although that's a bad idea.
        logger: Logger for this client.
            It defaults to ``logging.getLogger("websockets.client")``.
            See the :doc:`logging guide <../../topics/logging>` for details.
        legacy: Set to :obj:`True` to opt into the historical behavior of
            returning a :class:`ClientConnection`, without deprecation warning.
        create_connection: Factory for the :class:`ClientConnection` managing
            the connection. Set it to a wrapper or a subclass to customize
            connection handling.

    Any other keyword arguments are passed to :func:`~socket.create_connection`.
    For example, you can set ``address`` to a ``(host, port)`` tuple to connect
    to a different host and port from those found in ``uri``. This only changes
    the destination of the TCP connection. The host name from ``uri`` is still
    used in the TLS handshake for secure connections and in the ``Host`` header.

    Raises:
        InvalidURI: If ``uri`` isn't a valid WebSocket URI.
        InvalidProxy: If ``proxy`` isn't a valid proxy.
        OSError: If the TCP connection fails.
        InvalidHandshake: If the opening handshake fails.
        TimeoutError: If the opening handshake times out.

    """
    connecter = reconnect(
        uri,
        sock=sock,
        ssl=ssl,
        server_hostname=server_hostname,
        origin=origin,
        extensions=extensions,
        subprotocols=subprotocols,
        compression=compression,
        additional_headers=additional_headers,
        user_agent_header=user_agent_header,
        proxy=proxy,
        proxy_ssl=proxy_ssl,
        proxy_server_hostname=proxy_server_hostname,
        open_timeout=open_timeout,
        ping_interval=ping_interval,
        ping_timeout=ping_timeout,
        close_timeout=close_timeout,
        max_size=max_size,
        max_queue=max_queue,
        logger=logger,
        create_connection=create_connection,
        **kwargs,
    )
    # For backwards compatibility, connect defaults to the historical behavior.
    # For forwards compatibility, the future behavior can be chosen explicitly.
    if legacy is False:
        return connecter
    connection = connecter.connect()
    # Users can opt in to the historical behavior to remain unaffected when the
    # future behavior becomes the default.
    if legacy:
        connection.pending_legacy_warning = False
    return connection


def unix_reconnect(
    path: PathLike | None = None,
    uri: str | None = None,
    **kwargs: Any,
) -> reconnect:
    """
    Similar to :func:`unix_connect`, with support for automatic reconnection.

    Refer to the documentation of :func:`reconnect` for details on its behavior.

    """
    sock = kwargs.get("sock")
    if path is None and sock is None:
        raise ValueError("missing path argument")
    elif path is not None and sock is not None:
        raise ValueError("path is incompatible with sock")

    if uri is None:
        # Backwards compatibility: ssl used to be called ssl_context.
        if kwargs.get("ssl") is None and kwargs.get("ssl_context") is None:
            uri = "ws://localhost/"
        else:
            uri = "wss://localhost/"

    return reconnect(uri=uri, unix=True, path=path, **kwargs)


@overload
def unix_connect(
    path: PathLike | None = ...,
    uri: str | None = ...,
    *,
    legacy: Literal[True] | None = ...,
    **kwargs: Any,
) -> ClientConnection: ...


@overload
def unix_connect(
    path: PathLike | None = ...,
    uri: str | None = ...,
    *,
    legacy: Literal[False],
    **kwargs: Any,
) -> reconnect: ...


def unix_connect(
    path: PathLike | None = None,
    uri: str | None = None,
    *,
    legacy: bool | None = None,
    **kwargs: Any,
) -> ClientConnection | reconnect:
    """
    Connect to a WebSocket server listening on a Unix socket.

    This function accepts the same keyword arguments as :func:`connect`.

    It's only available on Unix.

    It's mainly useful for debugging servers listening on Unix sockets.

    Args:
        path: File system path to the Unix socket.
        uri: URI of the WebSocket server. ``uri`` defaults to
            ``ws://localhost/`` or, when a ``ssl`` is provided, to
            ``wss://localhost/``.

    """
    connecter = unix_reconnect(path, uri, **kwargs)
    # For backwards compatibility, connect defaults to the historical behavior.
    # For forwards compatibility, the future behavior can be chosen explicitly.
    if legacy is False:
        return connecter
    connection = connecter.connect()
    # Users can opt in to the historical behavior to remain unaffected when the
    # future behavior becomes the default.
    if legacy:
        connection.pending_legacy_warning = False
    return connection


try:
    from python_socks import ProxyType
    from python_socks.sync import Proxy as SocksProxy

except ImportError:

    def connect_socks_proxy(
        proxy: Proxy,
        ws_uri: WebSocketURI,
        deadline: Deadline,
        **kwargs: Any,
    ) -> socket.socket:
        raise ImportError("connecting through a SOCKS proxy requires python-socks")

else:
    SOCKS_PROXY_TYPES = {
        "socks5h": ProxyType.SOCKS5,
        "socks5": ProxyType.SOCKS5,
        "socks4a": ProxyType.SOCKS4,
        "socks4": ProxyType.SOCKS4,
    }

    SOCKS_PROXY_RDNS = {
        "socks5h": True,
        "socks5": False,
        "socks4a": True,
        "socks4": False,
    }

    def connect_socks_proxy(
        proxy: Proxy,
        ws_uri: WebSocketURI,
        deadline: Deadline,
        **kwargs: Any,
    ) -> socket.socket:
        """Connect via a SOCKS proxy and return the socket."""
        socks_proxy = SocksProxy(
            SOCKS_PROXY_TYPES[proxy.scheme],
            proxy.host,
            proxy.port,
            proxy.username,
            proxy.password,
            SOCKS_PROXY_RDNS[proxy.scheme],
        )
        kwargs.setdefault("timeout", deadline.timeout())
        # connect() is documented to raise OSError and TimeoutError.
        # Wrap other exceptions in ProxyError, a subclass of InvalidHandshake.
        try:
            return socks_proxy.connect(ws_uri.host, ws_uri.port, **kwargs)
        except (OSError, TimeoutError, socket.timeout):
            raise
        except Exception as exc:
            raise ProxyError("failed to connect to SOCKS proxy") from exc


def read_connect_response(sock: socket.socket, deadline: Deadline) -> Response:
    reader = StreamReader()
    parser = Response.parse(
        reader.read_line,
        reader.read_exact,
        reader.read_to_eof,
        proxy=True,
    )
    try:
        while True:
            sock.settimeout(deadline.timeout())
            data = sock.recv(4096)
            if data:
                reader.feed_data(data)
            else:
                reader.feed_eof()
            next(parser)
    except StopIteration as exc:
        assert isinstance(exc.value, Response)  # help mypy
        response = exc.value
        if 200 <= response.status_code < 300:
            return response
        else:
            raise InvalidProxyStatus(response)
    except socket.timeout:
        raise TimeoutError("timed out while connecting to HTTP proxy")
    except Exception as exc:
        raise InvalidProxyMessage(
            "did not receive a valid HTTP response from proxy"
        ) from exc
    finally:
        sock.settimeout(None)


def connect_http_proxy(
    proxy: Proxy,
    ws_uri: WebSocketURI,
    deadline: Deadline,
    *,
    user_agent_header: str | None = None,
    ssl: ssl_module.SSLContext | None = None,
    server_hostname: str | None = None,
    **kwargs: Any,
) -> socket.socket:
    # Connect socket

    kwargs.setdefault("timeout", deadline.timeout())
    sock = socket.create_connection((proxy.host, proxy.port), **kwargs)

    # Initialize TLS wrapper and perform TLS handshake

    if proxy.scheme == "https":
        if ssl is None:
            ssl = ssl_module.create_default_context()
        if server_hostname is None:
            server_hostname = proxy.host
        sock.settimeout(deadline.timeout())
        sock = ssl.wrap_socket(sock, server_hostname=server_hostname)
        sock.settimeout(None)

    # Send CONNECT request to the proxy and read response.

    request = prepare_connect_request(proxy, ws_uri, user_agent_header)
    sock.sendall(request)
    try:
        read_connect_response(sock, deadline)
    except Exception:
        sock.close()
        raise

    return sock


T = TypeVar("T")
F = TypeVar("F", bound=Callable[..., T])


class SSLSSLSocket:
    """
    Socket-like object providing TLS-in-TLS.

    Only methods that are used by websockets are implemented.

    """

    recv_bufsize = 65536

    def __init__(
        self,
        sock: socket.socket,
        ssl_context: ssl_module.SSLContext,
        server_hostname: str | None = None,
    ) -> None:
        self.incoming = ssl_module.MemoryBIO()
        self.outgoing = ssl_module.MemoryBIO()
        self.ssl_socket = sock
        self.ssl_object = ssl_context.wrap_bio(
            self.incoming,
            self.outgoing,
            server_hostname=server_hostname,
        )
        self.run_io(self.ssl_object.do_handshake)

    def run_io(self, func: Callable[..., T], *args: Any) -> T:
        while True:
            want_read = False
            want_write = False
            try:
                result = func(*args)
            except ssl_module.SSLWantReadError:
                want_read = True
            except ssl_module.SSLWantWriteError:  # pragma: no cover
                want_write = True

            # Write outgoing data in all cases.
            data = self.outgoing.read()
            if data:
                self.ssl_socket.sendall(data)

            # Read incoming data and retry on SSLWantReadError.
            if want_read:
                data = self.ssl_socket.recv(self.recv_bufsize)
                if data:
                    self.incoming.write(data)
                else:
                    self.incoming.write_eof()
                continue
            # Retry after writing outgoing data on SSLWantWriteError.
            if want_write:  # pragma: no cover
                continue
            # Return result if no error happened.
            return result

    def recv(self, buflen: int) -> bytes:
        try:
            return self.run_io(self.ssl_object.read, buflen)
        except ssl_module.SSLEOFError:
            return b""  # always ignore ragged EOFs

    def send(self, data: BytesLike) -> int:
        return self.run_io(self.ssl_object.write, data)

    def sendall(self, data: BytesLike) -> None:
        # adapted from ssl_module.SSLSocket.sendall()
        count = 0
        with memoryview(data) as view, view.cast("B") as byte_view:
            amount = len(byte_view)
            while count < amount:
                count += self.send(byte_view[count:])

    # recv_into(), recvfrom(), recvfrom_into(), sendto(), unwrap(), and the
    # flags argument aren't implemented because websockets doesn't need them.

    def __getattr__(self, name: str) -> Any:
        return getattr(self.ssl_socket, name)
