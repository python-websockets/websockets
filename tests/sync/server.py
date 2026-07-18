import contextlib
import ssl
import threading
import time
import urllib.parse

from websockets.sync.router import *
from websockets.sync.server import *


def get_uri(server, secure=None):
    if secure is None:
        secure = isinstance(server.socket, ssl.SSLSocket)  # hack
    protocol = "wss" if secure else "ws"
    host, port = server.socket.getsockname()
    return f"{protocol}://{host}:{port}"


def handler(ws):
    path = urllib.parse.urlparse(ws.request.path).path
    if path == "/":
        # The default path is an eval shell.
        for expr in ws:
            value = eval(expr)
            ws.send(str(value))
    elif path == "/crash":
        raise RuntimeError
    elif path == "/no-op":
        pass
    elif path == "/delay":
        delay = float(ws.recv())
        ws.close()
        time.sleep(delay)
    else:
        raise AssertionError(f"unexpected path: {path}")


class EvalShellMixin:
    def assertEval(self, client, expr, value):
        client.send(expr)
        self.assertEqual(client.recv(), value)


@contextlib.contextmanager
def run_server_or_router(
    serve_or_route,
    handler_or_url_map,
    host="localhost",
    port=0,
    **kwargs,
):
    with serve_or_route(handler_or_url_map, host, port, **kwargs) as server:
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            yield server
        finally:
            server.shutdown()
            thread.join()


def run_server(handler=handler, **kwargs):
    return run_server_or_router(serve, handler, **kwargs)


def run_router(url_map, **kwargs):
    return run_server_or_router(route, url_map, **kwargs)


@contextlib.contextmanager
def run_unix_server_or_router(
    path,
    unix_serve_or_route,
    handler_or_url_map,
    **kwargs,
):
    with unix_serve_or_route(handler_or_url_map, path, **kwargs) as server:
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            yield server
        finally:
            server.shutdown()
            thread.join()


def run_unix_server(path, handler=handler, **kwargs):
    return run_unix_server_or_router(path, unix_serve, handler, **kwargs)


def run_unix_router(path, url_map, **kwargs):
    return run_unix_server_or_router(path, unix_route, url_map, **kwargs)
