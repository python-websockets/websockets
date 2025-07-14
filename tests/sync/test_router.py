import http
import socket
import sys
import unittest
from unittest.mock import patch

from websockets.exceptions import InvalidStatus
from websockets.sync.client import connect, unix_connect
from websockets.sync.router import *

from ..utils import CLIENT_CONTEXT, SERVER_CONTEXT, temp_unix_socket_path
from .server import EvalShellMixin, get_uri, handler, run_router, run_unix_router


try:
    from werkzeug.routing import Map, Rule
except ImportError:
    pass


def echo(websocket, count):
    message = websocket.recv()
    for _ in range(count):
        websocket.send(message)


@unittest.skipUnless("werkzeug" in sys.modules, "werkzeug not installed")
class RouterTests(EvalShellMixin, unittest.TestCase):
    # This is a small realistic example of werkzeug's basic URL routing
    # features: path matching, parameter extraction, and default values.

    def test_router_matches_paths_and_extracts_parameters(self):
        """Router matches paths and extracts parameters."""
        url_map = Map(
            [
                Rule("/echo", defaults={"count": 1}, endpoint=echo),
                Rule("/echo/<int:count>", endpoint=echo),
            ]
        )
        with run_router(url_map) as server:
            with connect(get_uri(server) + "/echo") as client:
                client.send("hello")
                messages = list(client)
            self.assertEqual(messages, ["hello"])

            with connect(get_uri(server) + "/echo/3") as client:
                client.send("hello")
                messages = list(client)
            self.assertEqual(messages, ["hello", "hello", "hello"])

    @property  # avoids an import-time dependency on werkzeug
    def url_map(self):
        return Map(
            [
                Rule("/", endpoint=handler),
                Rule("/r", redirect_to="/"),
            ]
        )

    def test_route_with_query_string(self):
        """Router ignores query strings when matching paths."""
        with run_router(self.url_map) as server:
            with connect(get_uri(server) + "/?a=b") as client:
                self.assertEval(client, "ws.request.path", "/?a=b")

    def test_redirect(self):
        """Router redirects connections according to redirect_to."""
        with run_router(self.url_map, server_name="localhost") as server:
            with self.assertRaises(InvalidStatus) as raised:
                with connect(get_uri(server) + "/r"):
                    self.fail("did not raise")
            self.assertEqual(
                raised.exception.response.headers["Location"],
                "ws://localhost/",
            )

    def test_secure_redirect(self):
        """Router redirects connections to a wss:// URI when TLS is enabled."""
        with run_router(
            self.url_map, server_name="localhost", ssl=SERVER_CONTEXT
        ) as server:
            with self.assertRaises(InvalidStatus) as raised:
                with connect(get_uri(server) + "/r", ssl=CLIENT_CONTEXT):
                    self.fail("did not raise")
            self.assertEqual(
                raised.exception.response.headers["Location"],
                "wss://localhost/",
            )

    @patch("websockets.asyncio.client.connect.process_redirect", lambda _, exc: exc)
    def test_force_secure_redirect(self):
        """Router redirects ws:// connections to a wss:// URI when ssl=True."""
        with run_router(self.url_map, ssl=True) as server:
            redirect_uri = get_uri(server, secure=True)
            with self.assertRaises(InvalidStatus) as raised:
                with connect(get_uri(server) + "/r"):
                    self.fail("did not raise")
        self.assertEqual(
            raised.exception.response.headers["Location"],
            redirect_uri + "/",
        )

    @patch("websockets.asyncio.client.connect.process_redirect", lambda _, exc: exc)
    def test_force_redirect_server_name(self):
        """Router redirects connections to the host declared in server_name."""
        with run_router(self.url_map, server_name="other") as server:
            with self.assertRaises(InvalidStatus) as raised:
                with connect(get_uri(server) + "/r"):
                    self.fail("did not raise")
        self.assertEqual(
            raised.exception.response.headers["Location"],
            "ws://other/",
        )

    def test_not_found(self):
        """Router rejects requests to unknown paths with an HTTP 404 error."""
        with run_router(self.url_map) as server:
            with self.assertRaises(InvalidStatus) as raised:
                with connect(get_uri(server) + "/n"):
                    self.fail("did not raise")
        self.assertEqual(
            str(raised.exception),
            "server rejected WebSocket connection: HTTP 404",
        )

    def test_process_request_returning_none(self):
        """Router supports a process_request returning None."""

        def process_request(ws, request):
            ws.process_request_ran = True

        with run_router(self.url_map, process_request=process_request) as server:
            with connect(get_uri(server) + "/") as client:
                self.assertEval(client, "ws.process_request_ran", "True")

    def test_process_request_returning_response(self):
        """Router supports a process_request returning a response."""

        def process_request(ws, request):
            return ws.respond(http.HTTPStatus.FORBIDDEN, "Forbidden")

        with run_router(self.url_map, process_request=process_request) as server:
            with self.assertRaises(InvalidStatus) as raised:
                with connect(get_uri(server) + "/"):
                    self.fail("did not raise")
        self.assertEqual(
            str(raised.exception),
            "server rejected WebSocket connection: HTTP 403",
        )

    def test_custom_router_factory(self):
        """Router supports a custom router factory."""

        class MyRouter(Router):
            def handler(self, connection):
                connection.my_router_ran = True
                return super().handler(connection)

        with run_router(self.url_map, create_router=MyRouter) as server:
            with connect(get_uri(server)) as client:
                self.assertEval(client, "ws.my_router_ran", "True")


@unittest.skipUnless(hasattr(socket, "AF_UNIX"), "this test requires Unix sockets")
@unittest.skipUnless("werkzeug" in sys.modules, "werkzeug not installed")
class UnixRouterTests(EvalShellMixin, unittest.IsolatedAsyncioTestCase):
    def test_router_supports_unix_sockets(self):
        """Router supports Unix sockets."""
        url_map = Map([Rule("/echo/<int:count>", endpoint=echo)])
        with temp_unix_socket_path() as path:
            with run_unix_router(path, url_map):
                with unix_connect(path, "ws://localhost/echo/3") as client:
                    client.send("hello")
                    messages = list(client)
                self.assertEqual(messages, ["hello", "hello", "hello"])
