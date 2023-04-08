import contextlib

from websockets.asyncio.client import *
from websockets.asyncio.server import WebSocketServer

from .server import get_server_host_port


__all__ = [
    "run_client",
    "run_unix_client",
]


@contextlib.asynccontextmanager
async def run_client(wsuri_or_server, secure=None, resource_name="/", **kwargs):
    if isinstance(wsuri_or_server, str):
        wsuri = wsuri_or_server
    else:
        assert isinstance(wsuri_or_server, WebSocketServer)
        if secure is None:
            secure = "ssl" in kwargs
        protocol = "wss" if secure else "ws"
        host, port = get_server_host_port(wsuri_or_server)
        wsuri = f"{protocol}://{host}:{port}{resource_name}"
    async with connect(wsuri, **kwargs) as client:
        yield client


@contextlib.asynccontextmanager
async def run_unix_client(path, **kwargs):
    async with unix_connect(path, **kwargs) as client:
        yield client
