#!/usr/bin/env python

"""Echo server using the threading API."""

from websockets.sync.server import serve


def echo(websocket):
    for message in websocket:
        websocket.send(message)


def main():
    with serve(echo, "localhost", 8765) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
