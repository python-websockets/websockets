#!/usr/bin/env python

import asyncio
import http
import os
import signal

from websockets.asyncio.server import serve


async def echo(websocket):
    async for message in websocket:
        await websocket.send(message)


def health_check(connection, request):
    if request.path == "/healthz":
        return connection.respond(http.HTTPStatus.OK, "OK\n")


async def main():
    # Set the stop condition when receiving SIGINT.
    loop = asyncio.get_running_loop()
    stop = loop.create_future()
    loop.add_signal_handler(signal.SIGINT, stop.set_result, None)

    async with serve(
        echo,
        host="",
        port=int(os.environ["PORT"]),
        process_request=health_check,
    ):
        await stop


if __name__ == "__main__":
    asyncio.run(main())
