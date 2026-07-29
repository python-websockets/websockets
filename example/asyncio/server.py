#!/usr/bin/env python

"""Server example using the asyncio API."""

import asyncio
from websockets.asyncio.server import serve


async def hello(websocket):
    name = await websocket.recv()
    print(f"<<< {name}")

    greeting = f"Hello {name}!"

    await websocket.send(greeting)
    print(f">>> {greeting}")


async def main():
    server = await serve(hello, "localhost", 8765)
    await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
