#!/usr/bin/env python

"""Echo server using the trio API."""

import trio
from websockets.trio.server import serve


async def echo(websocket):
    async for message in websocket:
        await websocket.send(message)


if __name__ == "__main__":
    trio.run(serve, echo, 8765)
