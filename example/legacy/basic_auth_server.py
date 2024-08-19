#!/usr/bin/env python

# Server example with HTTP Basic Authentication over TLS

import asyncio

from websockets.legacy.auth import basic_auth_protocol_factory
from websockets.legacy.server import serve

async def hello(websocket):
    greeting = f"Hello {websocket.username}!"
    await websocket.send(greeting)

async def main():
    async with serve(
        hello, "localhost", 8765,
        create_protocol=basic_auth_protocol_factory(
            realm="example", credentials=("mary", "p@ssw0rd")
        ),
    ):
        await asyncio.get_running_loop().create_future()  # run forever

asyncio.run(main())
