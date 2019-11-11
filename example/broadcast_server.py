#!/usr/bin/env python
import asyncio
import time
import websockets

async def broadcast():
    while True:
        message = str(time.time())
        await asyncio.gather(
            *[ws.send(message) for ws in CLIENTS],
            return_exceptions=False,
        )
        await asyncio.sleep(2)

async def handler(websocket, path):
    CLIENTS.add(websocket)
    try:
        async for msg in websocket:
            pass
    except websockets.ConnectionClosedError:
        print("Connection closed")   
    finally:
        CLIENTS.remove(websocket)

CLIENTS = set()

loop = asyncio.get_event_loop()
loop.create_task(broadcast())

start_server = websockets.serve(handler, "localhost", 8765)

loop.run_until_complete(start_server)
try:
    loop.run_forever()
except KeyboardInterrupt:
    print("Exiting")
