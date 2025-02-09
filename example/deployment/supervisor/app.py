#!/usr/bin/env python

import asyncio
import signal

from websockets.asyncio.server import serve


async def echo(websocket):
    async for message in websocket:
        await websocket.send(message)


async def main():
    async with serve(echo, "", 8080, reuse_port=True) as server:
        loop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGTERM, server.close)
        await server.wait_closed()


if __name__ == "__main__":
    asyncio.run(main())
