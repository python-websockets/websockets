#!/usr/bin/env python

# WS echo server with HTTP endpoint at /health/

import asyncio
import http
import websockets

async def health_check(path, request_headers):
    if path == "/health/":
        return http.HTTPStatus.OK, [], b"OK\n"

async def echo(websocket, path):
    async for message in websocket:
        await websocket.send(message)

async def main():
    async with websockets.serve(
        echo, "localhost", 8765, process_request=health_check
    ):
        await asyncio.Future()  # run forever

asyncio.run(main)
