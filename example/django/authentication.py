#!/usr/bin/env python

import asyncio
import http
import urllib.parse

import django
import websockets

django.setup()

from sesame.utils import get_user


def get_sesame(path):
    """Utility function to extract sesame token from request path."""
    query = urllib.parse.urlparse(path).query
    params = urllib.parse.parse_qs(query)
    sesame = params.get("sesame", [])
    if len(sesame) == 1:
        return sesame[0]


class ServerProtocol(websockets.WebSocketServerProtocol):
    async def process_request(self, path, headers):
        """Authenticate users with a django-sesame token."""
        sesame = get_sesame(path)
        if sesame is None:
            return http.HTTPStatus.UNAUTHORIZED, [], b"Missing token\n"

        user = await asyncio.to_thread(get_user, sesame)
        if user is None:
            return http.HTTPStatus.UNAUTHORIZED, [], b"Invalid token\n"

        self.user = user


async def handler(websocket, path):
    await websocket.send(f"Hello {websocket.user}!")


async def main():
    async with websockets.serve(
        handler,
        "localhost",
        8888,
        create_protocol=ServerProtocol,
    ):
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())
