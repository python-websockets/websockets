import http
import sys
import unittest
from unittest.mock import patch

from websockets.exceptions import InvalidStatus
from websockets.trio.client import connect
from websockets.trio.router import *

from ..utils import CLIENT_CONTEXT, SERVER_CONTEXT, alist
from .server import EvalShellMixin, get_uri, handler, run_router
from .utils import IsolatedTrioTestCase


try:
    from werkzeug.routing import Map, Rule
except ImportError:
    pass


async def echo(websocket, count):
    message = await websocket.recv()
    for _ in range(count):
        await websocket.send(message)


@unittest.skipUnless("werkzeug" in sys.modules, "werkzeug not installed")
class RouterTests(EvalShellMixin, IsolatedTrioTestCase):
    # This is a small realistic example of werkzeug's basic URL routing
    # features: path matching, parameter extraction, and default values.

    async def test_router_matches_paths_and_extracts_parameters(self):
        """Router matches paths and extracts parameters."""
        url_map = Map(
            [
                Rule("/echo", defaults={"count": 1}, endpoint=echo),
                Rule("/echo/<int:count>", endpoint=echo),
            ]
        )
        async with run_router(url_map) as server:
            async with connect(get_uri(server) + "/echo") as client:
                await client.send("hello")
                messages = await alist(client)
            self.assertEqual(messages, ["hello"])

            async with connect(get_uri(server) + "/echo/3") as client:
                await client.send("hello")
                messages = await alist(client)
            self.assertEqual(messages, ["hello", "hello", "hello"])

    @property  # avoids an import-time dependency on werkzeug
    def url_map(self):
        return Map(
            [
                Rule("/", endpoint=handler),
                Rule("/r", redirect_to="/"),
            ]
        )

    async def test_route_with_query_string(self):
        """Router ignores query strings when matching paths."""
        async with run_router(self.url_map) as server:
            async with connect(get_uri(server) + "/?a=b") as client:
                await self.assertEval(client, "ws.request.path", "/?a=b")

    async def test_redirect(self):
        """Router redirects connections according to redirect_to."""
        async with run_router(self.url_map) as server:
            async with connect(get_uri(server) + "/r") as client:
                await self.assertEval(client, "ws.request.path", "/")

    async def test_secure_redirect(self):
        """Router redirects connections according to redirect_to when TLS is enabled."""
        async with run_router(self.url_map, ssl=SERVER_CONTEXT) as server:
            async with connect(get_uri(server) + "/r", ssl=CLIENT_CONTEXT) as client:
                await self.assertEval(client, "ws.request.path", "/")

    @patch("websockets.trio.client.connect.process_redirect", lambda _, exc: exc)
    async def test_force_secure_redirect(self):
        """Router redirects ws:// connections to a wss:// URI when ssl=True."""
        async with run_router(self.url_map, ssl=True) as server:
            redirect_uri = get_uri(server, secure=True)
            with self.assertRaises(InvalidStatus) as raised:
                async with connect(get_uri(server) + "/r"):
                    self.fail("did not raise")
        self.assertEqual(
            raised.exception.response.headers["Location"],
            redirect_uri + "/",
        )

    @patch("websockets.trio.client.connect.process_redirect", lambda _, exc: exc)
    async def test_force_redirect_server_name(self):
        """Router redirects connections to the host declared in server_name."""
        async with run_router(self.url_map, server_name="other") as server:
            with self.assertRaises(InvalidStatus) as raised:
                async with connect(get_uri(server) + "/r"):
                    self.fail("did not raise")
        self.assertEqual(
            raised.exception.response.headers["Location"],
            "ws://other/",
        )

    async def test_not_found(self):
        """Router rejects requests to unknown paths with an HTTP 404 error."""
        async with run_router(self.url_map) as server:
            with self.assertRaises(InvalidStatus) as raised:
                async with connect(get_uri(server) + "/n"):
                    self.fail("did not raise")
        self.assertEqual(
            str(raised.exception),
            "server rejected WebSocket connection: HTTP 404",
        )

    async def test_process_request_function_returning_none(self):
        """Router supports a process_request function returning None."""

        def process_request(ws, request):
            ws.process_request_ran = True

        async with run_router(self.url_map, process_request=process_request) as server:
            async with connect(get_uri(server) + "/") as client:
                await self.assertEval(client, "ws.process_request_ran", "True")

    async def test_process_request_coroutine_returning_none(self):
        """Router supports a process_request coroutine returning None."""

        async def process_request(ws, request):
            ws.process_request_ran = True

        async with run_router(self.url_map, process_request=process_request) as server:
            async with connect(get_uri(server) + "/") as client:
                await self.assertEval(client, "ws.process_request_ran", "True")

    async def test_process_request_function_returning_response(self):
        """Router supports a process_request function returning a response."""

        def process_request(ws, request):
            return ws.respond(http.HTTPStatus.FORBIDDEN, "Forbidden")

        async with run_router(self.url_map, process_request=process_request) as server:
            with self.assertRaises(InvalidStatus) as raised:
                async with connect(get_uri(server) + "/"):
                    self.fail("did not raise")
        self.assertEqual(
            str(raised.exception),
            "server rejected WebSocket connection: HTTP 403",
        )

    async def test_process_request_coroutine_returning_response(self):
        """Router supports a process_request coroutine returning a response."""

        async def process_request(ws, request):
            return ws.respond(http.HTTPStatus.FORBIDDEN, "Forbidden")

        async with run_router(self.url_map, process_request=process_request) as server:
            with self.assertRaises(InvalidStatus) as raised:
                async with connect(get_uri(server) + "/"):
                    self.fail("did not raise")
        self.assertEqual(
            str(raised.exception),
            "server rejected WebSocket connection: HTTP 403",
        )

    async def test_custom_router_factory(self):
        """Router supports a custom router factory."""

        class MyRouter(Router):
            async def handler(self, connection):
                connection.my_router_ran = True
                return await super().handler(connection)

        async with run_router(self.url_map, create_router=MyRouter) as server:
            async with connect(get_uri(server)) as client:
                await self.assertEval(client, "ws.my_router_ran", "True")
