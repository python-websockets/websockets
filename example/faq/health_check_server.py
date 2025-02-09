#!/usr/bin/env python

import asyncio
from http import HTTPStatus
from websockets.asyncio.server import serve

def health_check(connection, request):
    if request.path == "/healthz":
        return connection.respond(HTTPStatus.OK, "OK\n")

async def echo(websocket):
    async for message in websocket:
        await websocket.send(message)

async def main():
    async with serve(echo, "localhost", 8765, process_request=health_check) as server:
        await server.serve_forever()

asyncio.run(main())
