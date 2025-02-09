#!/usr/bin/env python

import asyncio
import os
import signal

from websockets.asyncio.server import unix_serve


async def echo(websocket):
    async for message in websocket:
        await websocket.send(message)


async def main():
    path = f"{os.environ['SUPERVISOR_PROCESS_NAME']}.sock"
    async with unix_serve(echo, path) as server:
        loop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGTERM, server.close)
        await server.wait_closed()


if __name__ == "__main__":
    asyncio.run(main())
