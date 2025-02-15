#!/usr/bin/env python

import asyncio
import datetime
import random

from websockets.asyncio.server import broadcast, serve

async def noop(websocket):
    await websocket.wait_closed()

async def show_time(server):
    while True:
        message = datetime.datetime.now(tz=datetime.timezone.utc).isoformat()
        broadcast(server.connections, message)
        await asyncio.sleep(random.random() * 2 + 1)

async def main():
    async with serve(noop, "localhost", 5678) as server:
        await show_time(server)

if __name__ == "__main__":
    asyncio.run(main())
