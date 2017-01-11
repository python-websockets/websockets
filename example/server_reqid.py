#!/usr/bin/env python

import asyncio
import json
import websockets

async def hello(websocket, path):
    request = await websocket.recv()
    request = json.loads(request)
    print("Received:", json.dumps(request, indent=2))

    response = {
        "id": request["id"],
        "error": None,
        "result": [110]
    }

    print("Sending:", json.dumps(response, indent=2))
    response = json.dumps(response)
    await websocket.send(response)

start_server = websockets.serve(hello, 'localhost', 8765)

asyncio.get_event_loop().run_until_complete(start_server)
asyncio.get_event_loop().run_forever()
