#!/usr/bin/env python

"""Server example using the trio API."""

import logging
logging.basicConfig(level=logging.DEBUG)

import functools
import trio
from websockets.trio.server import serve


async def hello(websocket):
    name = await websocket.recv()
    print(f"<<< {name}")

    greeting = f"Hello {name}!"

    await websocket.send(greeting)
    print(f">>> {greeting}")


async def main():
    async with trio.open_nursery() as nursery:
        server = await nursery.start(serve, hello, 8765)
        try:
            await trio.sleep_forever()
        except KeyboardInterrupt:
            await server.aclose()

if __name__ == "__main__":
    trio.run(main)
