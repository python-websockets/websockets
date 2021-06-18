from __future__ import annotations

import socket
import ssl
import threading
from typing import Any, Callable, Optional, Sequence, Type, Union

from ..connection import Event, State
from ..datastructures import Headers, HeadersLike
from ..extensions.base import ServerExtensionFactory
from ..extensions.permessage_deflate import enable_server_permessage_deflate
from ..http11 import Request
from ..server import ServerConnection
from ..typing import LoggerLike, Origin, Subprotocol
from .protocol import Protocol
from .utils import Deadline


__all__ = ["ServerProtocol", "serve", "unix_serve"]

HeadersLikeOrCallable = Union[HeadersLike, Callable[[str, Headers], HeadersLike]]


class ServerProtocol(Protocol):
    def __init__(
        self,
        sock: socket.socket,
        connection: ServerConnection,
        ping_interval: Optional[float] = None,
        ping_timeout: Optional[float] = None,
        close_timeout: Optional[float] = None,
    ) -> None:
        self.connection: ServerConnection
        super().__init__(
            sock,
            connection,
            ping_interval,
            ping_timeout,
            close_timeout,
        )
        self.request_rcvd = threading.Event()

    def handshake(self, timeout: Optional[float] = None) -> None:
        """
        Perform the opening handshake.

        """
        if not self.request_rcvd.wait(timeout):
            self.sock.close()
            self.recv_events_thread.join()
            raise TimeoutError("timed out waiting for handshake request")

        assert self.request is not None

        with self.send_context(expected_state=State.CONNECTING):
            self.response = self.connection.accept(self.request)
            # TODO EXTRA HEADERS???
            self.connection.send_response(self.response)

        if self.connection.state is not State.OPEN:
            self.recv_events_thread.join(self.close_timeout)
            if self.recv_events_thread.is_alive():
                self.sock.close()
                self.recv_events_thread.join()

        if self.request.exception is not None:
            raise self.request.exception

    def process_event(self, event: Event) -> None:
        """
        Process one incoming event.

        """
        # First event - handshake request.
        if self.request is None:
            assert isinstance(event, Request)
            self.request = event
            self.request_rcvd.set()
        # Later events - frames.
        else:
            super().process_event(event)


class Serve:
    def __init__(
        self,
        ws_handler: Callable[[ServerProtocol], Any],
        host: Optional[str] = None,
        port: Optional[int] = None,
        *,
        sock: Optional[socket.socket] = None,
        unix: bool = False,
        path: Optional[str] = None,
        ssl_context: Optional[ssl.SSLContext] = None,
        create_protocol: Optional[Type[ServerProtocol]] = None,
        open_timeout: Optional[float] = None,
        ping_interval: Optional[float] = None,
        ping_timeout: Optional[float] = None,
        close_timeout: Optional[float] = None,
        origins: Optional[Sequence[Optional[Origin]]] = None,
        extensions: Optional[Sequence[ServerExtensionFactory]] = None,
        subprotocols: Optional[Sequence[Subprotocol]] = None,
        extra_headers: Optional[HeadersLikeOrCallable] = None,
        max_size: Optional[int] = 2**20,
        compression: Optional[str] = "deflate",
        logger: Optional[LoggerLike] = None,
    ) -> None:
        if create_protocol is None:
            create_protocol = ServerProtocol

        if compression == "deflate":
            extensions = enable_server_permessage_deflate(extensions)
        elif compression is not None:
            raise ValueError(f"unsupported compression: {compression}")

        # Bind socket and listen

        if sock is None:
            if unix:
                if path is None:
                    raise TypeError("missing path argument")
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.bind(path)
                sock.listen()
            else:
                sock = socket.create_server((host, port))
        else:
            if path is not None:
                raise TypeError("path and sock arguments are incompatible")

        self.sock = sock

        def handle_one(sock: socket.socket, addr: Any) -> None:
            deadline = Deadline(open_timeout)

            # Wrap socket with TLS

            if ssl_context is not None:
                sock = ssl_context.wrap_socket(sock)

            # Initialize WebSocket connection

            connection = ServerConnection(
                origins,
                extensions,
                subprotocols,
                State.CONNECTING,
                max_size,
                logger,
            )

            # Initialize WebSocket protocol

            assert create_protocol is not None
            protocol = create_protocol(
                sock,
                connection,
                ping_interval,
                ping_timeout,
                close_timeout,
            )
            protocol.handshake(deadline.timeout())
            assert protocol.response is not None
            try:
                if protocol.response.status_code == 101:
                    ws_handler(protocol)
            finally:
                protocol.close()

        def handle() -> None:
            while True:
                sock, addr = self.sock.accept()
                threading.Thread(target=handle_one, args=(sock, addr)).start()

        threading.Thread(target=handle).start()


serve = Serve


def unix_serve(
    ws_handler: Callable[[ServerProtocol], Any],
    path: Optional[str] = None,
    **kwargs: Any,
) -> Serve:
    """
    Similar to :func:`serve`, but for listening on Unix sockets.

    This function is only available on Unix.

    It's useful for deploying a server behind a reverse proxy such as nginx.

    :param path: file system path to the Unix socket

    """
    return serve(ws_handler, path=path, unix=True, **kwargs)
