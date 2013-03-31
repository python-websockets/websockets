import tulip
import websockets

@tulip.coroutine
def hello(websocket, uri):
    name = yield from websocket.recv()
    websocket.send("Hello {}!".format(name))

websockets.serve(hello, 'localhost', 8765)

tulip.get_event_loop().run_forever()
