import asyncio
import socket


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


async def handler(ws):
    path = ws.request.path
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
        await ws.close()
        await asyncio.sleep(delay)
    else:
        raise AssertionError(f"unexpected path: {path}")


# This shortcut avoids repeating serve(handler, "localhost", 0) for every test.
args = handler, "localhost", 0


class EvalShellMixin:
    async def assertEval(self, client, expr, value):
        await client.send(expr)
        self.assertEqual(await client.recv(), value)
