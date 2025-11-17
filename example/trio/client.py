#!/usr/bin/env python

"""Client example using the trio API."""

import trio
from websockets.trio.client import connect


async def hello():
    async with connect("ws://localhost:8765") as websocket:
        name = input("What's your name? ")

        await websocket.send(name)
        print(f">>> {name}")

        greeting = await websocket.recv()
        print(f"<<< {greeting}")


if __name__ == "__main__":
    trio.run(hello)
