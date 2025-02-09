#!/usr/bin/env python

import asyncio
import os
import signal

from websockets.asyncio.server import serve


async def echo(websocket):
    async for message in websocket:
        await websocket.send(message)


async def main():
    port = 8000 + int(os.environ["SUPERVISOR_PROCESS_NAME"][-2:])
    async with serve(echo, "localhost", port) as server:
        loop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGTERM, server.close)
        await server.wait_closed()


if __name__ == "__main__":
    asyncio.run(main())
