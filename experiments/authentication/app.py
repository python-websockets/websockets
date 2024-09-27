#!/usr/bin/env python

import asyncio
import email.utils
import http
import http.cookies
import pathlib
import signal
import urllib.parse
import uuid

from websockets.asyncio.server import basic_auth as websockets_basic_auth, serve
from websockets.datastructures import Headers
from websockets.frames import CloseCode
from websockets.http11 import Response


# User accounts database

USERS = {}


def create_token(user, lifetime=1):
    """Create token for user and delete it once its lifetime is over."""
    token = uuid.uuid4().hex
    USERS[token] = user
    asyncio.get_running_loop().call_later(lifetime, USERS.pop, token)
    return token


def get_user(token):
    """Find user authenticated by token or return None."""
    return USERS.get(token)


# Utilities


def get_cookie(raw, key):
    cookie = http.cookies.SimpleCookie(raw)
    morsel = cookie.get(key)
    if morsel is not None:
        return morsel.value


def get_query_param(path, key):
    query = urllib.parse.urlparse(path).query
    params = urllib.parse.parse_qs(query)
    values = params.get(key, [])
    if len(values) == 1:
        return values[0]


# WebSocket handler


async def handler(websocket):
    try:
        user = websocket.username
    except AttributeError:
        return

    await websocket.send(f"Hello {user}!")
    message = await websocket.recv()
    assert message == f"Goodbye {user}."


CONTENT_TYPES = {
    ".css": "text/css",
    ".html": "text/html; charset=utf-8",
    ".ico": "image/x-icon",
    ".js": "text/javascript",
}


async def serve_html(connection, request):
    """Basic HTTP server implemented as a process_request hook."""
    user = get_query_param(request.path, "user")
    path = urllib.parse.urlparse(request.path).path
    if path == "/":
        if user is None:
            page = "index.html"
        else:
            page = "test.html"
    else:
        page = path[1:]

    try:
        template = pathlib.Path(__file__).with_name(page)
    except ValueError:
        pass
    else:
        if template.is_file():
            body = template.read_bytes()
            if user is not None:
                token = create_token(user)
                body = body.replace(b"TOKEN", token.encode())
            headers = Headers(
                {
                    "Date": email.utils.formatdate(usegmt=True),
                    "Connection": "close",
                    "Content-Length": str(len(body)),
                    "Content-Type": CONTENT_TYPES[template.suffix],
                }
            )
            return Response(200, "OK", headers, body)

    return connection.respond(http.HTTPStatus.NOT_FOUND, "Not found\n")


async def first_message_handler(websocket):
    """Handler that sends credentials in the first WebSocket message."""
    token = await websocket.recv()
    user = get_user(token)
    if user is None:
        await websocket.close(CloseCode.INTERNAL_ERROR, "authentication failed")
        return

    websocket.username = user
    await handler(websocket)


async def query_param_auth(connection, request):
    """Authenticate user from token in query parameter."""
    token = get_query_param(request.path, "token")
    if token is None:
        return connection.respond(http.HTTPStatus.UNAUTHORIZED, "Missing token\n")

    user = get_user(token)
    if user is None:
        return connection.respond(http.HTTPStatus.UNAUTHORIZED, "Invalid token\n")

    connection.username = user


async def cookie_auth(connection, request):
    """Authenticate user from token in cookie."""
    if "Upgrade" not in request.headers:
        template = pathlib.Path(__file__).with_name(request.path[1:])
        body = template.read_bytes()
        headers = Headers(
            {
                "Date": email.utils.formatdate(usegmt=True),
                "Connection": "close",
                "Content-Length": str(len(body)),
                "Content-Type": CONTENT_TYPES[template.suffix],
            }
        )
        return Response(200, "OK", headers, body)

    token = get_cookie(request.headers.get("Cookie", ""), "token")
    if token is None:
        return connection.respond(http.HTTPStatus.UNAUTHORIZED, "Missing token\n")

    user = get_user(token)
    if user is None:
        return connection.respond(http.HTTPStatus.UNAUTHORIZED, "Invalid token\n")

    connection.username = user


def check_credentials(username, password):
    """Authenticate user with HTTP Basic Auth."""
    return username == get_user(password)


basic_auth = websockets_basic_auth(check_credentials=check_credentials)


async def main():
    """Start one HTTP server and four WebSocket servers."""
    # Set the stop condition when receiving SIGINT or SIGTERM.
    loop = asyncio.get_running_loop()
    stop = loop.create_future()
    loop.add_signal_handler(signal.SIGINT, stop.set_result, None)
    loop.add_signal_handler(signal.SIGTERM, stop.set_result, None)

    async with (
        serve(handler, host="", port=8000, process_request=serve_html),
        serve(first_message_handler, host="", port=8001),
        serve(handler, host="", port=8002, process_request=query_param_auth),
        serve(handler, host="", port=8003, process_request=cookie_auth),
        serve(handler, host="", port=8004, process_request=basic_auth),
    ):
        print("Running on http://localhost:8000/")
        await stop
        print("\rExiting")


if __name__ == "__main__":
    asyncio.run(main())
