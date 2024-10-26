import dataclasses
import hmac
import http
import logging
import socket
import time
import unittest

from websockets.exceptions import (
    ConnectionClosedError,
    ConnectionClosedOK,
    InvalidStatus,
    NegotiationError,
)
from websockets.http11 import Request, Response
from websockets.sync.client import connect, unix_connect
from websockets.sync.server import *

from ..utils import (
    CLIENT_CONTEXT,
    MS,
    SERVER_CONTEXT,
    DeprecationTestCase,
    temp_unix_socket_path,
)
from .server import (
    EvalShellMixin,
    get_uri,
    handler,
    run_server,
    run_unix_server,
)


class ServerTests(EvalShellMixin, unittest.TestCase):
    def test_connection(self):
        """Server receives connection from client and the handshake succeeds."""
        with run_server() as server:
            with connect(get_uri(server)) as client:
                self.assertEval(client, "ws.protocol.state.name", "OPEN")

    def test_connection_handler_returns(self):
        """Connection handler returns."""
        with run_server() as server:
            with connect(get_uri(server) + "/no-op") as client:
                with self.assertRaises(ConnectionClosedOK) as raised:
                    client.recv()
                self.assertEqual(
                    str(raised.exception),
                    "received 1000 (OK); then sent 1000 (OK)",
                )

    def test_connection_handler_raises_exception(self):
        """Connection handler raises an exception."""
        with run_server() as server:
            with connect(get_uri(server) + "/crash") as client:
                with self.assertRaises(ConnectionClosedError) as raised:
                    client.recv()
                self.assertEqual(
                    str(raised.exception),
                    "received 1011 (internal error); "
                    "then sent 1011 (internal error)",
                )

    def test_existing_socket(self):
        """Server receives connection using a pre-existing socket."""
        with socket.create_server(("localhost", 0)) as sock:
            with run_server(sock=sock):
                uri = "ws://{}:{}/".format(*sock.getsockname())
                with connect(uri) as client:
                    self.assertEval(client, "ws.protocol.state.name", "OPEN")

    def test_select_subprotocol(self):
        """Server selects a subprotocol with the select_subprotocol callable."""

        def select_subprotocol(ws, subprotocols):
            ws.select_subprotocol_ran = True
            assert "chat" in subprotocols
            return "chat"

        with run_server(
            subprotocols=["chat"],
            select_subprotocol=select_subprotocol,
        ) as server:
            with connect(get_uri(server), subprotocols=["chat"]) as client:
                self.assertEval(client, "ws.select_subprotocol_ran", "True")
                self.assertEval(client, "ws.subprotocol", "chat")

    def test_select_subprotocol_rejects_handshake(self):
        """Server rejects handshake if select_subprotocol raises NegotiationError."""

        def select_subprotocol(ws, subprotocols):
            raise NegotiationError

        with run_server(select_subprotocol=select_subprotocol) as server:
            with self.assertRaises(InvalidStatus) as raised:
                with connect(get_uri(server)):
                    self.fail("did not raise")
            self.assertEqual(
                str(raised.exception),
                "server rejected WebSocket connection: HTTP 400",
            )

    def test_select_subprotocol_raises_exception(self):
        """Server returns an error if select_subprotocol raises an exception."""

        def select_subprotocol(ws, subprotocols):
            raise RuntimeError

        with run_server(select_subprotocol=select_subprotocol) as server:
            with self.assertRaises(InvalidStatus) as raised:
                with connect(get_uri(server)):
                    self.fail("did not raise")
            self.assertEqual(
                str(raised.exception),
                "server rejected WebSocket connection: HTTP 500",
            )

    def test_process_request_returns_none(self):
        """Server runs process_request and continues the handshake."""

        def process_request(ws, request):
            self.assertIsInstance(request, Request)
            ws.process_request_ran = True

        with run_server(process_request=process_request) as server:
            with connect(get_uri(server)) as client:
                self.assertEval(client, "ws.process_request_ran", "True")

    def test_process_request_returns_response(self):
        """Server aborts handshake if process_request returns a response."""

        def process_request(ws, request):
            return ws.respond(http.HTTPStatus.FORBIDDEN, "Forbidden")

        def handler(ws):
            self.fail("handler must not run")

        with run_server(handler, process_request=process_request) as server:
            with self.assertRaises(InvalidStatus) as raised:
                with connect(get_uri(server)):
                    self.fail("did not raise")
            self.assertEqual(
                str(raised.exception),
                "server rejected WebSocket connection: HTTP 403",
            )

    def test_process_request_raises_exception(self):
        """Server returns an error if process_request raises an exception."""

        def process_request(ws, request):
            raise RuntimeError

        with run_server(process_request=process_request) as server:
            with self.assertRaises(InvalidStatus) as raised:
                with connect(get_uri(server)):
                    self.fail("did not raise")
            self.assertEqual(
                str(raised.exception),
                "server rejected WebSocket connection: HTTP 500",
            )

    def test_process_response_returns_none(self):
        """Server runs process_response but keeps the handshake response."""

        def process_response(ws, request, response):
            self.assertIsInstance(request, Request)
            self.assertIsInstance(response, Response)
            ws.process_response_ran = True

        with run_server(process_response=process_response) as server:
            with connect(get_uri(server)) as client:
                self.assertEval(client, "ws.process_response_ran", "True")

    def test_process_response_modifies_response(self):
        """Server runs process_response and modifies the handshake response."""

        def process_response(ws, request, response):
            response.headers["X-ProcessResponse"] = "OK"

        with run_server(process_response=process_response) as server:
            with connect(get_uri(server)) as client:
                self.assertEqual(client.response.headers["X-ProcessResponse"], "OK")

    def test_process_response_replaces_response(self):
        """Server runs process_response and replaces the handshake response."""

        def process_response(ws, request, response):
            headers = response.headers.copy()
            headers["X-ProcessResponse"] = "OK"
            return dataclasses.replace(response, headers=headers)

        with run_server(process_response=process_response) as server:
            with connect(get_uri(server)) as client:
                self.assertEqual(client.response.headers["X-ProcessResponse"], "OK")

    def test_process_response_raises_exception(self):
        """Server returns an error if process_response raises an exception."""

        def process_response(ws, request, response):
            raise RuntimeError

        with run_server(process_response=process_response) as server:
            with self.assertRaises(InvalidStatus) as raised:
                with connect(get_uri(server)):
                    self.fail("did not raise")
            self.assertEqual(
                str(raised.exception),
                "server rejected WebSocket connection: HTTP 500",
            )

    def test_override_server(self):
        """Server can override Server header with server_header."""
        with run_server(server_header="Neo") as server:
            with connect(get_uri(server)) as client:
                self.assertEval(client, "ws.response.headers['Server']", "Neo")

    def test_remove_server(self):
        """Server can remove Server header with server_header."""
        with run_server(server_header=None) as server:
            with connect(get_uri(server)) as client:
                self.assertEval(client, "'Server' in ws.response.headers", "False")

    def test_compression_is_enabled(self):
        """Server enables compression by default."""
        with run_server() as server:
            with connect(get_uri(server)) as client:
                self.assertEval(
                    client,
                    "[type(ext).__name__ for ext in ws.protocol.extensions]",
                    "['PerMessageDeflate']",
                )

    def test_disable_compression(self):
        """Server disables compression."""
        with run_server(compression=None) as server:
            with connect(get_uri(server)) as client:
                self.assertEval(client, "ws.protocol.extensions", "[]")

    def test_logger(self):
        """Server accepts a logger argument."""
        logger = logging.getLogger("test")
        with run_server(logger=logger) as server:
            self.assertEqual(server.logger.name, logger.name)

    def test_custom_connection_factory(self):
        """Server runs ServerConnection factory provided in create_connection."""

        def create_connection(*args, **kwargs):
            server = ServerConnection(*args, **kwargs)
            server.create_connection_ran = True
            return server

        with run_server(create_connection=create_connection) as server:
            with connect(get_uri(server)) as client:
                self.assertEval(client, "ws.create_connection_ran", "True")

    def test_fileno(self):
        """Server provides a fileno attribute."""
        with run_server() as server:
            self.assertIsInstance(server.fileno(), int)

    def test_shutdown(self):
        """Server provides a shutdown method."""
        with run_server() as server:
            server.shutdown()
            # Check that the server socket is closed.
            with self.assertRaises(OSError):
                server.socket.accept()

    def test_handshake_fails(self):
        """Server receives connection from client but the handshake fails."""

        def remove_key_header(self, request):
            del request.headers["Sec-WebSocket-Key"]

        with run_server(process_request=remove_key_header) as server:
            with self.assertRaises(InvalidStatus) as raised:
                with connect(get_uri(server)):
                    self.fail("did not raise")
            self.assertEqual(
                str(raised.exception),
                "server rejected WebSocket connection: HTTP 400",
            )

    def test_timeout_during_handshake(self):
        """Server times out before receiving handshake request from client."""
        with run_server(open_timeout=MS) as server:
            with socket.create_connection(server.socket.getsockname()) as sock:
                self.assertEqual(sock.recv(4096), b"")

    def test_connection_closed_during_handshake(self):
        """Server reads EOF before receiving handshake request from client."""
        with run_server() as server:
            with socket.create_connection(server.socket.getsockname()):
                # Wait for the server to receive the connection, then close it.
                time.sleep(MS)

    def test_junk_handshake(self):
        """Server closes the connection when receiving non-HTTP request from client."""
        with self.assertLogs("websockets.server", logging.ERROR) as logs:
            with run_server() as server:
                with socket.create_connection(server.socket.getsockname()) as sock:
                    sock.send(b"HELO relay.invalid\r\n")
                    # Wait for the server to close the connection.
                    self.assertEqual(sock.recv(4096), b"")

        self.assertEqual(
            [record.getMessage() for record in logs.records],
            ["opening handshake failed"],
        )
        self.assertEqual(
            [str(record.exc_info[1]) for record in logs.records],
            ["invalid HTTP request line: HELO relay.invalid"],
        )


class SecureServerTests(EvalShellMixin, unittest.TestCase):
    def test_connection(self):
        """Server receives secure connection from client."""
        with run_server(ssl=SERVER_CONTEXT) as server:
            with connect(get_uri(server), ssl=CLIENT_CONTEXT) as client:
                self.assertEval(client, "ws.protocol.state.name", "OPEN")
                self.assertEval(client, "ws.socket.version()[:3]", "TLS")

    def test_timeout_during_tls_handshake(self):
        """Server times out before receiving TLS handshake request from client."""
        with run_server(ssl=SERVER_CONTEXT, open_timeout=MS) as server:
            with socket.create_connection(server.socket.getsockname()) as sock:
                self.assertEqual(sock.recv(4096), b"")

    def test_connection_closed_during_tls_handshake(self):
        """Server reads EOF before receiving TLS handshake request from client."""
        with run_server(ssl=SERVER_CONTEXT) as server:
            with socket.create_connection(server.socket.getsockname()):
                # Wait for the server to receive the connection, then close it.
                time.sleep(MS)


@unittest.skipUnless(hasattr(socket, "AF_UNIX"), "this test requires Unix sockets")
class UnixServerTests(EvalShellMixin, unittest.TestCase):
    def test_connection(self):
        """Server receives connection from client over a Unix socket."""
        with temp_unix_socket_path() as path:
            with run_unix_server(path):
                with unix_connect(path) as client:
                    self.assertEval(client, "ws.protocol.state.name", "OPEN")


@unittest.skipUnless(hasattr(socket, "AF_UNIX"), "this test requires Unix sockets")
class SecureUnixServerTests(EvalShellMixin, unittest.TestCase):
    def test_connection(self):
        """Server receives secure connection from client over a Unix socket."""
        with temp_unix_socket_path() as path:
            with run_unix_server(path, ssl=SERVER_CONTEXT):
                with unix_connect(path, ssl=CLIENT_CONTEXT) as client:
                    self.assertEval(client, "ws.protocol.state.name", "OPEN")
                    self.assertEval(client, "ws.socket.version()[:3]", "TLS")


class ServerUsageErrorsTests(unittest.TestCase):
    def test_unix_without_path_or_sock(self):
        """Unix server requires path when sock isn't provided."""
        with self.assertRaises(ValueError) as raised:
            unix_serve(handler)
        self.assertEqual(
            str(raised.exception),
            "missing path argument",
        )

    def test_unix_with_path_and_sock(self):
        """Unix server rejects path when sock is provided."""
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.addCleanup(sock.close)
        with self.assertRaises(ValueError) as raised:
            unix_serve(handler, path="/", sock=sock)
        self.assertEqual(
            str(raised.exception),
            "path and sock arguments are incompatible",
        )

    def test_invalid_subprotocol(self):
        """Server rejects single value of subprotocols."""
        with self.assertRaises(TypeError) as raised:
            serve(handler, subprotocols="chat")
        self.assertEqual(
            str(raised.exception),
            "subprotocols must be a list, not a str",
        )

    def test_unsupported_compression(self):
        """Server rejects incorrect value of compression."""
        with self.assertRaises(ValueError) as raised:
            serve(handler, compression=False)
        self.assertEqual(
            str(raised.exception),
            "unsupported compression: False",
        )


class BasicAuthTests(EvalShellMixin, unittest.IsolatedAsyncioTestCase):
    def test_valid_authorization(self):
        """basic_auth authenticates client with HTTP Basic Authentication."""
        with run_server(
            process_request=basic_auth(credentials=("hello", "iloveyou")),
        ) as server:
            with connect(
                get_uri(server),
                additional_headers={"Authorization": "Basic aGVsbG86aWxvdmV5b3U="},
            ) as client:
                self.assertEval(client, "ws.username", "hello")

    def test_missing_authorization(self):
        """basic_auth rejects client without credentials."""
        with run_server(
            process_request=basic_auth(credentials=("hello", "iloveyou")),
        ) as server:
            with self.assertRaises(InvalidStatus) as raised:
                with connect(get_uri(server)):
                    self.fail("did not raise")
            self.assertEqual(
                str(raised.exception),
                "server rejected WebSocket connection: HTTP 401",
            )

    def test_unsupported_authorization(self):
        """basic_auth rejects client with unsupported credentials."""
        with run_server(
            process_request=basic_auth(credentials=("hello", "iloveyou")),
        ) as server:
            with self.assertRaises(InvalidStatus) as raised:
                with connect(
                    get_uri(server),
                    additional_headers={"Authorization": "Negotiate ..."},
                ):
                    self.fail("did not raise")
            self.assertEqual(
                str(raised.exception),
                "server rejected WebSocket connection: HTTP 401",
            )

    def test_authorization_with_unknown_username(self):
        """basic_auth rejects client with unknown username."""
        with run_server(
            process_request=basic_auth(credentials=("hello", "iloveyou")),
        ) as server:
            with self.assertRaises(InvalidStatus) as raised:
                with connect(
                    get_uri(server),
                    additional_headers={"Authorization": "Basic YnllOnlvdWxvdmVtZQ=="},
                ):
                    self.fail("did not raise")
            self.assertEqual(
                str(raised.exception),
                "server rejected WebSocket connection: HTTP 401",
            )

    def test_authorization_with_incorrect_password(self):
        """basic_auth rejects client with incorrect password."""
        with run_server(
            process_request=basic_auth(credentials=("hello", "changeme")),
        ) as server:
            with self.assertRaises(InvalidStatus) as raised:
                with connect(
                    get_uri(server),
                    additional_headers={"Authorization": "Basic aGVsbG86aWxvdmV5b3U="},
                ):
                    self.fail("did not raise")
            self.assertEqual(
                str(raised.exception),
                "server rejected WebSocket connection: HTTP 401",
            )

    def test_list_of_credentials(self):
        """basic_auth accepts a list of hard coded credentials."""
        with run_server(
            process_request=basic_auth(
                credentials=[
                    ("hello", "iloveyou"),
                    ("bye", "youloveme"),
                ]
            ),
        ) as server:
            with connect(
                get_uri(server),
                additional_headers={"Authorization": "Basic YnllOnlvdWxvdmVtZQ=="},
            ) as client:
                self.assertEval(client, "ws.username", "bye")

    def test_check_credentials(self):
        """basic_auth accepts a check_credentials function."""

        def check_credentials(username, password):
            return hmac.compare_digest(password, "iloveyou")

        with run_server(
            process_request=basic_auth(check_credentials=check_credentials),
        ) as server:
            with connect(
                get_uri(server),
                additional_headers={"Authorization": "Basic aGVsbG86aWxvdmV5b3U="},
            ) as client:
                self.assertEval(client, "ws.username", "hello")

    def test_without_credentials_or_check_credentials(self):
        """basic_auth requires either credentials or check_credentials."""
        with self.assertRaises(ValueError) as raised:
            basic_auth()
        self.assertEqual(
            str(raised.exception),
            "provide either credentials or check_credentials",
        )

    def test_with_credentials_and_check_credentials(self):
        """basic_auth requires only one of credentials and check_credentials."""
        with self.assertRaises(ValueError) as raised:
            basic_auth(
                credentials=("hello", "iloveyou"),
                check_credentials=lambda: False,  # pragma: no cover
            )
        self.assertEqual(
            str(raised.exception),
            "provide either credentials or check_credentials",
        )

    def test_bad_credentials(self):
        """basic_auth receives an unsupported credentials argument."""
        with self.assertRaises(TypeError) as raised:
            basic_auth(credentials=42)
        self.assertEqual(
            str(raised.exception),
            "invalid credentials argument: 42",
        )

    def test_bad_list_of_credentials(self):
        """basic_auth receives an unsupported credentials argument."""
        with self.assertRaises(TypeError) as raised:
            basic_auth(credentials=[42])
        self.assertEqual(
            str(raised.exception),
            "invalid credentials argument: [42]",
        )


class BackwardsCompatibilityTests(DeprecationTestCase):
    def test_ssl_context_argument(self):
        """Server supports the deprecated ssl_context argument."""
        with self.assertDeprecationWarning("ssl_context was renamed to ssl"):
            with run_server(ssl_context=SERVER_CONTEXT) as server:
                with connect(get_uri(server), ssl=CLIENT_CONTEXT):
                    pass

    def test_web_socket_server_class(self):
        with self.assertDeprecationWarning("WebSocketServer was renamed to Server"):
            from websockets.sync.server import WebSocketServer
        self.assertIs(WebSocketServer, Server)
