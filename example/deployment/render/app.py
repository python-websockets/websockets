#!/usr/bin/env python

import asyncio
import http
import signal

from websockets.asyncio.server import serve


async def echo(websocket):
    async for message in websocket:
        await websocket.send(message)


def health_check(connection, request):
    if request.path == "/healthz":
        return connection.respond(http.HTTPStatus.OK, "OK\n")


async def main():
    async with serve(echo, "", 8080, process_request=health_check) as server:
        loop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGTERM, server.close)
        await server.wait_closed()


if __name__ == "__main__":
    asyncio.run(main())
