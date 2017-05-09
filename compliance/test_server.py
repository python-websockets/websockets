import logging

import asyncio
import websockets


logging.basicConfig(level=logging.WARNING)

# Uncomment this line to make only websockets more verbose.
# logging.getLogger('websockets').setLevel(logging.DEBUG)


@asyncio.coroutine
def echo(ws, path):
    while True:
        try:
            msg = yield from ws.recv()
            yield from ws.send(msg)
        except websockets.ConnectionClosed:
            break


start_server = websockets.serve(
    echo, '127.0.0.1', 8642, max_size=2 ** 25, max_queue=1)

try:
    asyncio.get_event_loop().run_until_complete(start_server)
    asyncio.get_event_loop().run_forever()
except KeyboardInterrupt:
    pass
