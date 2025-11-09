import contextlib
import functools
import socket
import urllib.parse

import trio

from websockets.trio.server import *


def get_host_port(listeners):
    for listener in listeners:
        if listener.socket.family == socket.AF_INET:  # pragma: no branch
            return listener.socket.getsockname()
    raise AssertionError("expected at least one IPv4 socket")


def get_uri(server, secure=False):
    protocol = "wss" if secure else "ws"
    host, port = get_host_port(server.listeners)
    return f"{protocol}://{host}:{port}"


async def handler(ws):
    path = urllib.parse.urlparse(ws.request.path).path
    if path == "/":
        # The default path is an eval shell.
        async for expr in ws:
            value = eval(expr)
            await ws.send(str(value))
    elif path == "/crash":
        raise RuntimeError
    elif path == "/no-op":
        pass
    elif path == "/delay":
        delay = float(await ws.recv())
        await ws.aclose()
        await trio.sleep(delay)
    else:
        raise AssertionError(f"unexpected path: {path}")


kwargs = {"handler": handler, "port": 0, "host": "localhost"}


@contextlib.asynccontextmanager
async def run_server(**overrides):
    merged_kwargs = {**kwargs, **overrides}
    async with trio.open_nursery() as nursery:
        server = await nursery.start(functools.partial(serve, **merged_kwargs))
        try:
            yield server
        finally:
            # Run all tasks to guarantee that any exceptions are raised.
            # Otherwise, canceling the nursery could hide errors.
            await trio.testing.wait_all_tasks_blocked()
            nursery.cancel_scope.cancel()


class EvalShellMixin:
    async def assertEval(self, client, expr, value):
        await client.send(expr)
        self.assertEqual(await client.recv(), value)
