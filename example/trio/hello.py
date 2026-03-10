#!/usr/bin/env python

"""Client using the trio API."""

import trio
from websockets.trio.client import connect


async def hello():
    async with connect("ws://localhost:8765") as websocket:
        await websocket.send("Hello world!")
        message = await websocket.recv()
        print(message)


if __name__ == "__main__":
    trio.run(hello)
