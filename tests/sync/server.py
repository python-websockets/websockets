import contextlib
import threading

from websockets.sync.server import *


def crash(ws):
    raise RuntimeError


def do_nothing(ws):
    pass


def eval_shell(ws):
    for expr in ws:
        value = eval(expr)
        ws.send(str(value))


class EvalShellMixin:
    def assertEval(self, client, expr, value):
        client.send(expr)
        self.assertEqual(client.recv(), value)


@contextlib.contextmanager
def run_server(handler=eval_shell, host="localhost", port=0, **kwargs):
    with serve(handler, host, port, **kwargs) as server:
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            yield server
        finally:
            server.shutdown()
            thread.join()


@contextlib.contextmanager
def run_unix_server(path, handler=eval_shell, **kwargs):
    with unix_serve(handler, path, **kwargs) as server:
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            yield server
        finally:
            server.shutdown()
            thread.join()
