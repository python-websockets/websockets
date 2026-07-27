import contextlib
import functools
import socket
import ssl
import urllib.parse

import trio

from websockets.trio.router import route
from websockets.trio.server import serve


def get_host_port(listeners):
    for listener in listeners:
        if listener.socket.family == socket.AF_INET:  # pragma: no branch
            return listener.socket.getsockname()
    raise AssertionError("expected at least one IPv4 socket")


def get_uri(server, secure=None):
    if secure is None:
        secure = any(
            isinstance(cell.cell_contents, ssl.SSLContext)
            for cell in server.handler.__closure__
        )  # l33t hack
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


class EvalShellMixin:
    async def assertEval(self, client, expr, value):
        await client.send(expr)
        self.assertEqual(await client.recv(), value)


kwargs = {"port": 0, "host": "localhost"}


@contextlib.asynccontextmanager
async def run_server_or_route(
    serve_or_route,
    handler_or_url_map,
    **overrides,
):
    merged_kwargs = {**kwargs, **overrides}
    async with trio.open_nursery() as nursery:
        server = await nursery.start(
            functools.partial(serve_or_route, handler_or_url_map, **merged_kwargs)
        )
        try:
            yield server
        finally:
            # Run all tasks to guarantee that any exceptions are raised.
            # Otherwise, canceling the nursery could hide errors.
            await trio.testing.wait_all_tasks_blocked()
            nursery.cancel_scope.cancel()


def run_server(handler=handler, **overrides):
    return run_server_or_route(serve, handler, **overrides)


def run_router(url_map, **overrides):
    return run_server_or_route(route, url_map, **overrides)
