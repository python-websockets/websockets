import contextlib
import socket

from websockets.asyncio.server import *


def get_server_host_port(server):
    for sock in server.sockets:
        if sock.family == socket.AF_INET:
            return sock.getsockname()
    else:
        raise AssertionError("expected at least one IPv4 socket")


async def crash(ws):
    raise RuntimeError


async def do_nothing(ws):
    pass


async def eval_shell(ws):
    async for expr in ws:
        value = eval(expr)
        await ws.send(str(value))


class EvalShellMixin:
    async def assertEval(self, client, expr, value):
        await client.send(expr)
        self.assertEqual(await client.recv(), value)


@contextlib.asynccontextmanager
async def run_server(handler=eval_shell, host="localhost", port=0, **kwargs):
    async with serve(handler, host, port, **kwargs) as server:
        yield server


@contextlib.asynccontextmanager
async def run_unix_server(path, handler=eval_shell, **kwargs):
    async with unix_serve(handler, path, **kwargs) as server:
        yield server
