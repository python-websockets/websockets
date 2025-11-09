#!/usr/bin/env python

"""Server example using the trio API."""

import trio
from websockets.trio.server import serve


async def hello(websocket):
    name = await websocket.recv()
    print(f"<<< {name}")

    greeting = f"Hello {name}!"

    await websocket.send(greeting)
    print(f">>> {greeting}")


if __name__ == "__main__":
    trio.run(serve, hello, 8765)
