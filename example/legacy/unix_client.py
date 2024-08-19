#!/usr/bin/env python

# WS client example connecting to a Unix socket

import asyncio
import os.path

from websockets.legacy.client import unix_connect

async def hello():
    socket_path = os.path.join(os.path.dirname(__file__), "socket")
    async with unix_connect(socket_path) as websocket:
        name = input("What's your name? ")
        await websocket.send(name)
        print(f">>> {name}")

        greeting = await websocket.recv()
        print(f"<<< {greeting}")

asyncio.run(hello())
