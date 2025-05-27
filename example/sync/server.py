#!/usr/bin/env python

"""Server example using the threading API."""

from websockets.sync.server import serve


def hello(websocket):
    name = websocket.recv()
    print(f"<<< {name}")

    greeting = f"Hello {name}!"

    websocket.send(greeting)
    print(f">>> {greeting}")


def main():
    with serve(hello, "localhost", 8765) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
