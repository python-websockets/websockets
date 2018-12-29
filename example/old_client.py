#!/usr/bin/env python

# WS client example for old Python versions

import asyncio
import websockets

async def hello():
    websocket = await websockets.connect(
        'ws://localhost:8765/')

    try:
        name = input("What's your name? ")

        await websocket.send(name)
        print("> {}".format(name))

        greeting = await websocket.recv()
        print("< {}".format(greeting))

    finally:
        await websocket.close()

asyncio.get_event_loop().run_until_complete(hello())
