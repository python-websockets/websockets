#!/usr/bin/env python

from websockets.sync.client import connect

def hello():
    uri = "ws://localhost:8765"
    with connect(uri) as websocket:
        name = input("What's your name? ")

        websocket.send(name)
        print(f">>> {name}")

        greeting = websocket.recv()
        print(f"<<< {greeting}")

if __name__ == "__main__":
    hello()
