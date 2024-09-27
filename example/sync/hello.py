#!/usr/bin/env python

"""Client using the threading API."""

from websockets.sync.client import connect


def hello():
    with connect("ws://localhost:8765") as websocket:
        websocket.send("Hello world!")
        message = websocket.recv()
        print(message)


if __name__ == "__main__":
    hello()
