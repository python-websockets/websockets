import tulip
import websockets

@tulip.coroutine
def hello():
    websocket = yield from websockets.connect('ws://localhost:8765/')
    name = input("What's your name? ")
    websocket.send(name)
    print("> {}".format(name))
    greeting = yield from websocket.recv()
    print("< {}".format(greeting))
    yield from websocket.wait_close()

tulip.get_event_loop().run_until_complete(hello())
