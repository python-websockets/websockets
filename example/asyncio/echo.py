#!/usr/bin/env python

"""Echo server using the asyncio API."""

import asyncio
from websockets.asyncio.server import serve


async def echo(websocket):
    async for message in websocket:
        await websocket.send(message)


async def main():
    server = await serve(echo, "localhost", 8765)
    await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
