#!/usr/bin/env python

import asyncio
import datetime
import random

from websockets.asyncio.server import serve

async def show_time(websocket):
    while True:
        message = datetime.datetime.now(tz=datetime.timezone.utc).isoformat()
        await websocket.send(message)
        await asyncio.sleep(random.random() * 2 + 1)

async def main():
    server = await serve(show_time, "localhost", 5678)
    await server.serve_forever()

if __name__ == "__main__":
    asyncio.run(main())
