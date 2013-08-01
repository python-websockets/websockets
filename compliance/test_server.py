import logging

import tulip
import websockets


logging.basicConfig(level=logging.WARNING)
#logging.getLogger('websockets').setLevel(logging.DEBUG)


class EchoServerProtocol(websockets.WebSocketServerProtocol):

    """WebSocket server protocol that echoes messages synchronously."""

    @tulip.coroutine
    def read_message(self):
        msg = yield from super(EchoServerProtocol, self).read_message()
        if msg is not None:
            self.send(msg)
        return msg


@tulip.coroutine
def noop(ws, uri):
    yield from ws.worker


websockets.serve(noop, '127.0.0.1', 8642, klass=EchoServerProtocol)

try:
    tulip.get_event_loop().run_forever()
except KeyboardInterrupt:
    pass
