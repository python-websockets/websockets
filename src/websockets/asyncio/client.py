from __future__ import annotations

import asyncio
from types import TracebackType
from typing import Any, Generator, Optional, Sequence, Type

from ..client import ClientProtocol
from ..datastructures import HeadersLike
from ..extensions.base import ClientExtensionFactory
from ..extensions.permessage_deflate import enable_client_permessage_deflate
from ..headers import validate_subprotocols
from ..http import USER_AGENT
from ..http11 import Response
from ..protocol import CONNECTING, Event
from ..typing import LoggerLike, Origin, Subprotocol
from ..uri import parse_uri
from .compatibility import asyncio_timeout
from .connection import Connection


__all__ = ["connect", "unix_connect", "ClientConnection"]


class ClientConnection(Connection):
    """
    :mod:`asyncio` implementation of a WebSocket client connection.

    :class:`ClientConnection` provides :meth:`recv` and :meth:`send` coroutines
    for receiving and sending messages.

    It supports asynchronous iteration to receive messages::

        async for message in websocket:
            await process(message)

    The iterator exits normally when the connection is closed with close code
    1000 (OK) or 1001 (going away) or without a close code. It raises a
    :exc:`~websockets.exceptions.ConnectionClosedError` when the connection is
    closed with any other code.

    Args:
        protocol: Sans-I/O connection.
        close_timeout: Timeout for closing the connection in seconds.

    """

    def __init__(
        self,
        protocol: ClientProtocol,
        *,
        close_timeout: Optional[float] = 10,
    ) -> None:
        self.protocol: ClientProtocol
        super().__init__(
            protocol,
            close_timeout=close_timeout,
        )
        self.response_rcvd: asyncio.Future[None] = self.loop.create_future()

    async def handshake(
        self,
        additional_headers: Optional[HeadersLike] = None,
        user_agent_header: Optional[str] = USER_AGENT,
    ) -> None:
        """
        Perform the opening handshake.

        """
        async with self.send_context(expected_state=CONNECTING):
            self.request = self.protocol.connect()
            if additional_headers is not None:
                self.request.headers.update(additional_headers)
            if user_agent_header is not None:
                self.request.headers["User-Agent"] = user_agent_header
            self.protocol.send_request(self.request)

        # May raise CancelledError if open_timeout is exceeded.
        await self.response_rcvd

        if self.response is None:
            raise ConnectionError("connection closed during handshake")

        if self.protocol.handshake_exc is not None:
            try:
                async with asyncio_timeout(self.close_timeout):
                    await self.connection_lost_waiter
            finally:
                raise self.protocol.handshake_exc

    def process_event(self, event: Event) -> None:
        """
        Process one incoming event.

        """
        # First event - handshake response.
        if self.response is None:
            assert isinstance(event, Response)
            self.response = event
            self.response_rcvd.set_result(None)
        # Later events - frames.
        else:
            super().process_event(event)

    def connection_lost(self, exc: Optional[Exception]) -> None:
        try:
            super().connection_lost(exc)
        finally:
            # If the connection is closed during the handshake, unblock it.
            if not self.response_rcvd.done():
                self.response_rcvd.set_result(None)


class connect:
    """
    Connect to the WebSocket server at ``uri``.

    This coroutine returns a :class:`ClientConnection` instance, which you can
    use to send and receive messages.

    :func:`connect` may be used as a context manager::

        async with websockets.asyncio.client.connect(...) as websocket:
            ...

    The connection is closed automatically when exiting the context.

    Args:
        uri: URI of the WebSocket server.
        server_hostname: Host name for the TLS handshake. ``server_hostname``
            overrides the host name from ``uri``.
        origin: Value of the ``Origin`` header, for servers that require it.
        extensions: List of supported extensions, in order in which they
            should be negotiated and run.
        subprotocols: List of supported subprotocols, in order of decreasing
            preference.
        additional_headers (HeadersLike | None): Arbitrary HTTP headers to add
            to the handshake request.
        user_agent_header: Value of  the ``User-Agent`` request header.
            It defaults to ``"Python/x.y.z websockets/X.Y"``.
            Setting it to :obj:`None` removes the header.
        compression: The "permessage-deflate" extension is enabled by default.
            Set ``compression`` to :obj:`None` to disable it. See the
            :doc:`compression guide <../../topics/compression>` for details.
        open_timeout: Timeout for opening the connection in seconds.
            :obj:`None` disables the timeout.
        close_timeout: Timeout for closing the connection in seconds.
            :obj:`None` disables the timeout.
        max_size: Maximum size of incoming messages in bytes.
            :obj:`None` disables the limit.
        logger: Logger for this client.
            It defaults to ``logging.getLogger("websockets.client")``.
            See the :doc:`logging guide <../../topics/logging>` for details.
        create_connection: Factory for the :class:`ClientConnection` managing
            the connection. Set it to a wrapper or a subclass to customize
            connection handling.

    Any other keyword arguments are passed to the event loop's
    :meth:`~asyncio.loop.create_connection` method.

    For example:

    * You can set ``ssl`` to a :class:`~ssl.SSLContext` to enforce TLS settings.
      When connecting to a ``wss://`` URI, if ``ssl`` isn't provided, a TLS
      context is created with :func:`~ssl.create_default_context`.

    * You can set ``server_hostname`` to override the host name from ``uri`` in
      the TLS handshake.

    * You can set ``host`` and ``port`` to connect to a different host and port
      from those found in ``uri``. This only changes the destination of the TCP
      connection. The host name from ``uri`` is still used in the TLS handshake
      for secure connections and in the ``Host`` header.

    * You can set ``sock`` to provide a preexisting TCP socket. You may call
      :func:`socket.create_connection` (not to be confused with the event loop's
      :meth:`~asyncio.loop.create_connection` method) to create a suitable
      client socket and customize it.

    Raises:
        InvalidURI: If ``uri`` isn't a valid WebSocket URI.
        OSError: If the TCP connection fails.
        InvalidHandshake: If the opening handshake fails.
        TimeoutError: If the opening handshake times out.

    """

    def __init__(
        self,
        uri: str,
        *,
        # WebSocket
        origin: Optional[Origin] = None,
        extensions: Optional[Sequence[ClientExtensionFactory]] = None,
        subprotocols: Optional[Sequence[Subprotocol]] = None,
        additional_headers: Optional[HeadersLike] = None,
        user_agent_header: Optional[str] = USER_AGENT,
        compression: Optional[str] = "deflate",
        # Timeouts
        open_timeout: Optional[float] = 10,
        close_timeout: Optional[float] = 10,
        # Limits
        max_size: Optional[int] = 2**20,
        # Logging
        logger: Optional[LoggerLike] = None,
        # Escape hatch for advanced customization
        create_connection: Optional[Type[ClientConnection]] = None,
        # Other keyword arguments are passed to loop.create_connection
        **kwargs: Any,
    ) -> None:

        wsuri = parse_uri(uri)

        if wsuri.secure:
            if kwargs.get("ssl") is None:
                kwargs["ssl"] = True
            kwargs.setdefault("server_hostname", wsuri.host)
        else:
            if kwargs.get("ssl") is not None:
                raise TypeError("ssl argument is incompatible with a ws:// URI")

        if subprotocols is not None:
            validate_subprotocols(subprotocols)

        if compression == "deflate":
            extensions = enable_client_permessage_deflate(extensions)
        elif compression is not None:
            raise ValueError(f"unsupported compression: {compression}")

        if create_connection is None:
            create_connection = ClientConnection

        def factory() -> ClientConnection:
            # This is a protocol in websockets.
            protocol = ClientProtocol(
                wsuri,
                origin=origin,
                extensions=extensions,
                subprotocols=subprotocols,
                max_size=max_size,
                logger=logger,
            )
            # This is a connection in websockets and a protocol in asyncio.
            connection = create_connection(
                protocol,
                close_timeout=close_timeout,
            )
            return connection

        loop = asyncio.get_running_loop()
        if kwargs.pop("unix", False):
            self._create_connection = loop.create_unix_connection(factory, **kwargs)
        else:
            if kwargs.get("sock") is None:
                kwargs.setdefault("host", wsuri.host)
                kwargs.setdefault("port", wsuri.port)
            self._create_connection = loop.create_connection(factory, **kwargs)

        self._handshake_args = (
            additional_headers,
            user_agent_header,
        )

        self._open_timeout = open_timeout

    # async with connect(...) as ...: ...

    async def __aenter__(self) -> ClientConnection:
        return await self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        await self.connection.close()

    # ... = await connect(...)

    def __await__(self) -> Generator[Any, None, ClientConnection]:
        # Create a suitable iterator by calling __await__ on a coroutine.
        return self.__await_impl__().__await__()

    async def __await_impl__(self) -> ClientConnection:
        try:
            async with asyncio_timeout(self._open_timeout):
                _transport, self.connection = await self._create_connection
                try:
                    await self.connection.handshake(*self._handshake_args)
                except (Exception, asyncio.CancelledError):
                    self.connection.transport.close()
                    raise
                else:
                    return self.connection
        except TimeoutError:
            # Re-raise exception with an informative error message.
            raise TimeoutError("timed out during handshake") from None

    # ... = yield from connect(...) - remove when dropping Python < 3.10

    __iter__ = __await__


def unix_connect(
    path: Optional[str] = None,
    uri: Optional[str] = None,
    **kwargs: Any,
) -> connect:
    """
    Connect to a WebSocket server listening on a Unix socket.

    This function accepts the same keyword arguments as :func:`connect`.

    It's only available on Unix.

    It's mainly useful for debugging servers listening on Unix sockets.

    Args:
        path: File system path to the Unix socket.
        uri: URI of the WebSocket server. ``uri`` defaults to
            ``ws://localhost/`` or, when a ``ssl`` argument is provided, to
            ``wss://localhost/``.

    """
    if uri is None:
        if kwargs.get("ssl") is None:
            uri = "ws://localhost/"
        else:
            uri = "wss://localhost/"
    return connect(uri=uri, unix=True, path=path, **kwargs)
