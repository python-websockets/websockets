#!/usr/bin/env python

# WS client example with HTTP Basic Authentication

import asyncio

from websockets.legacy.client import connect

async def hello():
    uri = "ws://mary:p@ssw0rd@localhost:8765"
    async with connect(uri) as websocket:
        greeting = await websocket.recv()
        print(greeting)

asyncio.run(hello())
