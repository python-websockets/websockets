import logging

import asyncio
import websockets


logging.basicConfig(level=logging.WARNING)
#logging.getLogger('websockets').setLevel(logging.DEBUG)


class EchoServerProtocol(websockets.WebSocketServerProtocol):
    """
    WebSocket server protocol that echoes messages synchronously.

    """
    def __init__(self, *args, **kwargs):
        kwargs['max_size'] = 2 ** 25
        super().__init__(*args, **kwargs)

    @asyncio.coroutine
    def read_message(self):
        msg = yield from super().read_message()
        if msg is not None:
            yield from self.send(msg)
        return msg


@asyncio.coroutine
def noop(ws, path):
    yield from ws.worker_task


start_server = websockets.serve(noop, '127.0.0.1', 8642, klass=EchoServerProtocol)

try:
    asyncio.get_event_loop().run_until_complete(start_server)
    asyncio.get_event_loop().run_forever()
except KeyboardInterrupt:
    pass
