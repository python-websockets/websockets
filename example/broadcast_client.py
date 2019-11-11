#!/usr/bin/env python
import asyncio
import websockets

async def client():
    uri = "ws://localhost:8765"
    async with websockets.connect(uri) as websocket:

        while True:
            message = await websocket.recv()
            print("message:", message)

try:
    asyncio.get_event_loop().run_until_complete(client())
except KeyboardInterrupt:
    print("Exiting")
except websockets.exceptions.ConnectionClosedError:
    print("Connection lost")
