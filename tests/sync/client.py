import contextlib

from websockets.sync.client import *
from websockets.sync.server import Server


__all__ = [
    "run_client",
    "run_unix_client",
]


@contextlib.contextmanager
def run_client(wsuri_or_server, secure=None, resource_name="/", **kwargs):
    if isinstance(wsuri_or_server, str):
        wsuri = wsuri_or_server
    else:
        assert isinstance(wsuri_or_server, Server)
        if secure is None:
            # Backwards compatibility: ssl used to be called ssl_context.
            secure = "ssl" in kwargs or "ssl_context" in kwargs
        protocol = "wss" if secure else "ws"
        host, port = wsuri_or_server.socket.getsockname()
        wsuri = f"{protocol}://{host}:{port}{resource_name}"
    with connect(wsuri, **kwargs) as client:
        yield client


@contextlib.contextmanager
def run_unix_client(path, **kwargs):
    with unix_connect(path, **kwargs) as client:
        yield client
