#!/usr/bin/env python

import asyncio
import http
import signal
import sys
import time

from websockets.asyncio.server import serve


async def slow_echo(websocket):
    async for message in websocket:
        # Block the event loop! This allows saturating a single asyncio
        # process without opening an impractical number of connections.
        time.sleep(0.1)  # 100ms
        await websocket.send(message)


def health_check(connection, request):
    if request.path == "/healthz":
        return connection.respond(http.HTTPStatus.OK, "OK\n")
    if request.path == "/inemuri":
        loop = asyncio.get_running_loop()
        loop.call_later(1, time.sleep, 10)
        return connection.respond(http.HTTPStatus.OK, "Sleeping for 10s\n")
    if request.path == "/seppuku":
        loop = asyncio.get_running_loop()
        loop.call_later(1, sys.exit, 69)
        return connection.respond(http.HTTPStatus.OK, "Terminating\n")


async def main():
    async with serve(slow_echo, "", 80, process_request=health_check) as server:
        loop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGTERM, server.close)
        await server.wait_closed()


if __name__ == "__main__":
    asyncio.run(main())
