#!/usr/bin/env python

import asyncio
import signal

from websockets.asyncio.client import connect

async def client():
    async with connect("ws://localhost:8765") as websocket:
        # Close the connection when receiving SIGTERM.
        loop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGTERM, loop.create_task, websocket.close())

        # Process messages received on the connection.
        async for message in websocket:
            ...

asyncio.run(client())
