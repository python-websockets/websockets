import asyncio
import contextlib
import socket

from websockets.asyncio.server import *


def get_host_port(server):
    for sock in server.sockets:
        if sock.family == socket.AF_INET:  # pragma: no branch
            return sock.getsockname()
    raise AssertionError("expected at least one IPv4 socket")


def get_uri(server):
    secure = server.server._ssl_context is not None  # hack
    protocol = "wss" if secure else "ws"
    host, port = get_host_port(server)
    return f"{protocol}://{host}:{port}"


async def eval_shell(ws):
    async for expr in ws:
        value = eval(expr)
        await ws.send(str(value))


class EvalShellMixin:
    async def assertEval(self, client, expr, value):
        await client.send(expr)
        self.assertEqual(await client.recv(), value)


async def crash(ws):
    raise RuntimeError


async def do_nothing(ws):
    pass


async def keep_running(ws):
    delay = float(await ws.recv())
    await ws.close()
    await asyncio.sleep(delay)


@contextlib.asynccontextmanager
async def run_server(handler=eval_shell, host="localhost", port=0, **kwargs):
    async with serve(handler, host, port, **kwargs) as server:
        yield server


@contextlib.asynccontextmanager
async def run_unix_server(path, handler=eval_shell, **kwargs):
    async with unix_serve(handler, path, **kwargs) as server:
        yield server
