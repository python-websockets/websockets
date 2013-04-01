import logging

import tulip
import websockets


logging.basicConfig(level=logging.WARNING)
#logging.getLogger('websockets').setLevel(logging.DEBUG)


@tulip.coroutine
def echo(ws, uri):
    try:
        while True:
            msg = yield from ws.recv()
            if msg is None:
                break
            ws.send(msg)
    except Exception:
        logging.exception("Server exception in test case")


websockets.serve(echo, '127.0.0.1', 8642)

try:
    tulip.get_event_loop().run_forever()
except KeyboardInterrupt:
    pass
