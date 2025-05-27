#!/usr/bin/env python

"""Client example using the threading API."""

from websockets.sync.client import connect


def hello():
    with connect("ws://localhost:8765") as websocket:
        name = input("What's your name? ")

        websocket.send(name)
        print(f">>> {name}")

        greeting = websocket.recv()
        print(f"<<< {greeting}")


if __name__ == "__main__":
    hello()
