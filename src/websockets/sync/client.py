from __future__ import annotations

import socket
import ssl
import threading
from types import TracebackType
from typing import Any, Optional, Sequence, Type

from ..client import ClientConnection
from ..connection import Event, State
from ..datastructures import HeadersLike
from ..extensions.base import ClientExtensionFactory
from ..extensions.permessage_deflate import enable_client_permessage_deflate
from ..headers import validate_subprotocols
from ..http11 import Response
from ..typing import LoggerLike, Origin, Subprotocol
from ..uri import parse_uri
from .protocol import Protocol
from .utils import Deadline


__all__ = ["ClientProtocol", "connect", "unix_connect"]


class ClientProtocol(Protocol):
    def __init__(
        self,
        sock: socket.socket,
        connection: ClientConnection,
        *,
        close_timeout: Optional[float] = None,
    ) -> None:
        self.connection: ClientConnection
        super().__init__(
            sock,
            connection,
            close_timeout=close_timeout,
        )
        self.response_rcvd = threading.Event()

    def handshake(
        self,
        extra_headers: Optional[HeadersLike] = None,
        timeout: Optional[float] = None,
    ) -> None:
        """
        Perform the opening handshake.

        """
        assert isinstance(self.connection, ClientConnection)

        with self.send_context(expected_state=State.CONNECTING):
            self.request = self.connection.connect()
            if extra_headers is not None:
                self.request.headers.update(extra_headers)
            self.connection.send_request(self.request)

        if not self.response_rcvd.wait(timeout):
            self.sock.close()
            self.recv_events_thread.join()
            raise TimeoutError("timed out waiting for handshake response")

        assert self.response is not None

        if self.connection.state is not State.OPEN:
            self.recv_events_thread.join(self.close_timeout)
            if self.recv_events_thread.is_alive():
                self.sock.close()
                self.recv_events_thread.join()

        if self.response.exception is not None:
            raise self.response.exception

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


class Connect:
    def __init__(
        self,
        uri: str,
        *,
        # TCP/TLS (unix and path are only for unix_connect)
        sock: Optional[socket.socket] = None,
        ssl_context: Optional[ssl.SSLContext] = None,
        server_hostname: Optional[str] = None,
        unix: bool = False,
        path: Optional[str] = None,
        # WebSocket
        origin: Optional[Origin] = None,
        extensions: Optional[Sequence[ClientExtensionFactory]] = None,
        subprotocols: Optional[Sequence[Subprotocol]] = None,
        extra_headers: Optional[HeadersLike] = None,
        compression: Optional[str] = "deflate",
        # Timeouts
        open_timeout: Optional[float] = None,
        close_timeout: Optional[float] = None,
        # Limits
        max_size: Optional[int] = 2**20,
        # Logging
        logger: Optional[LoggerLike] = None,
        # Escape hatch for advanced customization (undocumented)
        create_protocol: Optional[Type[ClientProtocol]] = None,
    ) -> None:

        # Process parameters

        wsuri = parse_uri(uri)

        if unix:
            if path is None and sock is None:
                raise TypeError("missing path argument")
            elif path is not None and sock is not None:
                raise TypeError("path and sock arguments are incompatible")
        else:
            assert path is None  # private argument, only set by unix_connect()

        if subprotocols is not None:
            validate_subprotocols(subprotocols)

        if compression == "deflate":
            extensions = enable_client_permessage_deflate(extensions)
        elif compression is not None:
            raise ValueError(f"unsupported compression: {compression}")

        deadline = Deadline(open_timeout)

        if create_protocol is None:
            create_protocol = ClientProtocol

        # Connect socket

        if sock is None:
            if unix:
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.settimeout(deadline.timeout())
                assert path is not None  # validated above -- this is for mpypy
                sock.connect(path)
            else:
                sock = socket.create_connection(
                    (wsuri.host, wsuri.port),
                    deadline.timeout(),
                )

        # Wrap socket with TLS

        if wsuri.secure:
            if ssl_context is None:
                ssl_context = ssl.create_default_context()
            if server_hostname is None:
                server_hostname = wsuri.host
            sock.settimeout(deadline.timeout())
            sock = ssl_context.wrap_socket(sock, server_hostname=server_hostname)
        elif ssl_context is not None:
            raise TypeError("ssl_context argument is incompatible with a ws:// URI")

        # Initialize WebSocket connection

        connection = ClientConnection(
            wsuri,
            origin,
            extensions,
            subprotocols,
            State.CONNECTING,
            max_size,
            logger,
        )

        # Initialize WebSocket protocol

        self.protocol = create_protocol(
            sock,
            connection,
            close_timeout=close_timeout,
        )
        self.protocol.handshake(
            extra_headers,
            deadline.timeout(),
        )

        # Reset socket timeout

        sock.settimeout(None)

    # with connect(...)

    def __enter__(self) -> ClientProtocol:
        return self.protocol

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        self.protocol.close()


connect = Connect


def unix_connect(
    path: Optional[str] = None,
    uri: str = "ws://localhost/",
    **kwargs: Any,
) -> Connect:
    """
    Similar to :func:`connect`, but for connecting to a Unix socket.

    This function is only available on Unix.

    It's mainly useful for debugging servers listening on Unix sockets.

    Args:
        path: file system path to the Unix socket.
        uri: URI of the WebSocket server; the host is used in the TLS
            handshake for secure connections and in the ``Host`` header.

    """
    return connect(uri=uri, unix=True, path=path, **kwargs)
