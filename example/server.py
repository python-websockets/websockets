import tulip
import websockets

@tulip.coroutine
def hello(websocket, uri):
    name = yield from websocket.recv()
    print("< {}".format(name))
    greeting = "Hello {}!".format(name)
    print("> {}".format(greeting))
    websocket.send(greeting)

websockets.serve(hello, 'localhost', 8765)

tulip.get_event_loop().run_forever()
