#!/usr/bin/env python

import asyncio
import signal

from websockets.asyncio.server import serve

async def handler(websocket):
    async for message in websocket:
        ...

async def server():
    async with serve(handler, "localhost", 8765) as server:
        # Close the server when receiving SIGTERM.
        loop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGTERM, server.close)
        await server.wait_closed()

asyncio.run(server())
