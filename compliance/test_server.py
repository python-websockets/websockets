import logging

import tulip
import websockets


logging.basicConfig(level=logging.WARNING)
#logging.getLogger('websockets').setLevel(logging.DEBUG)


class EchoServerProtocol(websockets.WebSocketServerProtocol):

    """WebSocket server protocol that echoes messages synchronously."""

    def handle_message(self, msg):
        self.send(msg)

    def handle_eof(self):
        pass

    def handle_exception(self, exc):
        raise exc


@tulip.coroutine
def noop(ws, uri):
    yield from ws.close_waiter


websockets.serve(noop, '127.0.0.1', 8642, klass=EchoServerProtocol)

try:
    tulip.get_event_loop().run_forever()
except KeyboardInterrupt:
    pass
