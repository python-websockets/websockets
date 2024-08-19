#!/usr/bin/env python

# WS server example listening on a Unix socket

import asyncio
import os.path

from websockets.legacy.server import unix_serve

async def hello(websocket):
    name = await websocket.recv()
    print(f"<<< {name}")

    greeting = f"Hello {name}!"

    await websocket.send(greeting)
    print(f">>> {greeting}")

async def main():
    socket_path = os.path.join(os.path.dirname(__file__), "socket")
    async with unix_serve(hello, socket_path):
        await asyncio.get_running_loop().create_future()  # run forever

asyncio.run(main())
