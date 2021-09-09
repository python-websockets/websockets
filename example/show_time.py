#!/usr/bin/env python

# WS server that sends messages at random intervals

import asyncio
import datetime
import random
import websockets

async def time(websocket):
    while True:
        now = datetime.datetime.utcnow().isoformat() + "Z"
        await websocket.send(now)
        await asyncio.sleep(random.random() * 3)

async def main():
    async with websockets.serve(time, "localhost", 5678):
        await asyncio.Future()  # run forever

asyncio.run(main())
