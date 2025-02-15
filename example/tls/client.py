#!/usr/bin/env python

import pathlib
import ssl

from websockets.sync.client import connect

ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
localhost_pem = pathlib.Path(__file__).with_name("localhost.pem")
ssl_context.load_verify_locations(localhost_pem)

def hello():
    uri = "wss://localhost:8765"
    with connect(uri, ssl=ssl_context) as websocket:
        name = input("What's your name? ")

        websocket.send(name)
        print(f">>> {name}")

        greeting = websocket.recv()
        print(f"<<< {greeting}")

if __name__ == "__main__":
    hello()
