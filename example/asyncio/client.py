#!/usr/bin/env python

"""Client example using the asyncio API."""

import asyncio

from websockets.asyncio.client import connect


async def hello():
    async with connect("ws://localhost:8765") as websocket:
        name = input("What's your name? ")

        await websocket.send(name)
        print(f">>> {name}")

        greeting = await websocket.recv()
        print(f"<<< {greeting}")


if __name__ == "__main__":
    asyncio.run(hello())
