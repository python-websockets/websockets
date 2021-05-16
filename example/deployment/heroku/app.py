#!/usr/bin/env python

import asyncio
import os

import websockets

async def echo(websocket, path):
    async for message in websocket:
        await websocket.send(message)

async def main():
    async with websockets.serve(echo, "", int(os.environ["PORT"])):
        await asyncio.Future()  # run forever

asyncio.run(main())
