import contextlib
import ssl
import threading

from websockets.sync.server import *


def get_uri(server):
    secure = isinstance(server.socket, ssl.SSLSocket)  # hack
    protocol = "wss" if secure else "ws"
    host, port = server.socket.getsockname()
    return f"{protocol}://{host}:{port}"


def handler(ws):
    path = ws.request.path
    if path == "/":
        # The default path is an eval shell.
        for expr in ws:
            value = eval(expr)
            ws.send(str(value))
    elif path == "/crash":
        raise RuntimeError
    elif path == "/no-op":
        pass
    else:
        raise AssertionError(f"unexpected path: {path}")


class EvalShellMixin:
    def assertEval(self, client, expr, value):
        client.send(expr)
        self.assertEqual(client.recv(), value)


@contextlib.contextmanager
def run_server(handler=handler, host="localhost", port=0, **kwargs):
    with serve(handler, host, port, **kwargs) as server:
        thread = threading.Thread(target=server.serve_forever)
        thread.start()

        # HACK: since the sync server doesn't track connections (yet), we record
        # a reference to the thread handling the most recent connection, then we
        # can wait for that thread to terminate when exiting the context.
        handler_thread = None
        original_handler = server.handler

        def handler(sock, addr):
            nonlocal handler_thread
            handler_thread = threading.current_thread()
            original_handler(sock, addr)

        server.handler = handler

        try:
            yield server
        finally:
            server.shutdown()
            thread.join()

            # HACK: wait for the thread handling the most recent connection.
            if handler_thread is not None:
                handler_thread.join()


@contextlib.contextmanager
def run_unix_server(path, handler=handler, **kwargs):
    with unix_serve(handler, path, **kwargs) as server:
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            yield server
        finally:
            server.shutdown()
            thread.join()
