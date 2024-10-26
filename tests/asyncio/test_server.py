import asyncio
import dataclasses
import hmac
import http
import logging
import socket
import unittest

from websockets.asyncio.client import connect, unix_connect
from websockets.asyncio.compatibility import TimeoutError, asyncio_timeout
from websockets.asyncio.server import *
from websockets.exceptions import (
    ConnectionClosedError,
    ConnectionClosedOK,
    InvalidStatus,
    NegotiationError,
)
from websockets.http11 import Request, Response

from ..utils import (
    CLIENT_CONTEXT,
    MS,
    SERVER_CONTEXT,
    temp_unix_socket_path,
)
from .server import (
    EvalShellMixin,
    args,
    get_host_port,
    get_uri,
    handler,
)


class ServerTests(EvalShellMixin, unittest.IsolatedAsyncioTestCase):
    async def test_connection(self):
        """Server receives connection from client and the handshake succeeds."""
        async with serve(*args) as server:
            async with connect(get_uri(server)) as client:
                await self.assertEval(client, "ws.protocol.state.name", "OPEN")

    async def test_connection_handler_returns(self):
        """Connection handler returns."""
        async with serve(*args) as server:
            async with connect(get_uri(server) + "/no-op") as client:
                with self.assertRaises(ConnectionClosedOK) as raised:
                    await client.recv()
                self.assertEqual(
                    str(raised.exception),
                    "received 1000 (OK); then sent 1000 (OK)",
                )

    async def test_connection_handler_raises_exception(self):
        """Connection handler raises an exception."""
        async with serve(*args) as server:
            async with connect(get_uri(server) + "/crash") as client:
                with self.assertRaises(ConnectionClosedError) as raised:
                    await client.recv()
                self.assertEqual(
                    str(raised.exception),
                    "received 1011 (internal error); "
                    "then sent 1011 (internal error)",
                )

    async def test_existing_socket(self):
        """Server receives connection using a pre-existing socket."""
        with socket.create_server(("localhost", 0)) as sock:
            async with serve(handler, sock=sock, host=None, port=None):
                uri = "ws://{}:{}/".format(*sock.getsockname())
                async with connect(uri) as client:
                    await self.assertEval(client, "ws.protocol.state.name", "OPEN")

    async def test_select_subprotocol(self):
        """Server selects a subprotocol with the select_subprotocol callable."""

        def select_subprotocol(ws, subprotocols):
            ws.select_subprotocol_ran = True
            assert "chat" in subprotocols
            return "chat"

        async with serve(
            *args,
            subprotocols=["chat"],
            select_subprotocol=select_subprotocol,
        ) as server:
            async with connect(get_uri(server), subprotocols=["chat"]) as client:
                await self.assertEval(client, "ws.select_subprotocol_ran", "True")
                await self.assertEval(client, "ws.subprotocol", "chat")

    async def test_select_subprotocol_rejects_handshake(self):
        """Server rejects handshake if select_subprotocol raises NegotiationError."""

        def select_subprotocol(ws, subprotocols):
            raise NegotiationError

        async with serve(*args, select_subprotocol=select_subprotocol) as server:
            with self.assertRaises(InvalidStatus) as raised:
                async with connect(get_uri(server)):
                    self.fail("did not raise")
            self.assertEqual(
                str(raised.exception),
                "server rejected WebSocket connection: HTTP 400",
            )

    async def test_select_subprotocol_raises_exception(self):
        """Server returns an error if select_subprotocol raises an exception."""

        def select_subprotocol(ws, subprotocols):
            raise RuntimeError

        async with serve(*args, select_subprotocol=select_subprotocol) as server:
            with self.assertRaises(InvalidStatus) as raised:
                async with connect(get_uri(server)):
                    self.fail("did not raise")
            self.assertEqual(
                str(raised.exception),
                "server rejected WebSocket connection: HTTP 500",
            )

    async def test_process_request_returns_none(self):
        """Server runs process_request and continues the handshake."""

        def process_request(ws, request):
            self.assertIsInstance(request, Request)
            ws.process_request_ran = True

        async with serve(*args, process_request=process_request) as server:
            async with connect(get_uri(server)) as client:
                await self.assertEval(client, "ws.process_request_ran", "True")

    async def test_async_process_request_returns_none(self):
        """Server runs async process_request and continues the handshake."""

        async def process_request(ws, request):
            self.assertIsInstance(request, Request)
            ws.process_request_ran = True

        async with serve(*args, process_request=process_request) as server:
            async with connect(get_uri(server)) as client:
                await self.assertEval(client, "ws.process_request_ran", "True")

    async def test_process_request_returns_response(self):
        """Server aborts handshake if process_request returns a response."""

        def process_request(ws, request):
            return ws.respond(http.HTTPStatus.FORBIDDEN, "Forbidden")

        async def handler(ws):
            self.fail("handler must not run")

        async with serve(handler, *args[1:], process_request=process_request) as server:
            with self.assertRaises(InvalidStatus) as raised:
                async with connect(get_uri(server)):
                    self.fail("did not raise")
            self.assertEqual(
                str(raised.exception),
                "server rejected WebSocket connection: HTTP 403",
            )

    async def test_async_process_request_returns_response(self):
        """Server aborts handshake if async process_request returns a response."""

        async def process_request(ws, request):
            return ws.respond(http.HTTPStatus.FORBIDDEN, "Forbidden")

        async def handler(ws):
            self.fail("handler must not run")

        async with serve(handler, *args[1:], process_request=process_request) as server:
            with self.assertRaises(InvalidStatus) as raised:
                async with connect(get_uri(server)):
                    self.fail("did not raise")
            self.assertEqual(
                str(raised.exception),
                "server rejected WebSocket connection: HTTP 403",
            )

    async def test_process_request_raises_exception(self):
        """Server returns an error if process_request raises an exception."""

        def process_request(ws, request):
            raise RuntimeError

        async with serve(*args, process_request=process_request) as server:
            with self.assertRaises(InvalidStatus) as raised:
                async with connect(get_uri(server)):
                    self.fail("did not raise")
            self.assertEqual(
                str(raised.exception),
                "server rejected WebSocket connection: HTTP 500",
            )

    async def test_async_process_request_raises_exception(self):
        """Server returns an error if async process_request raises an exception."""

        async def process_request(ws, request):
            raise RuntimeError

        async with serve(*args, process_request=process_request) as server:
            with self.assertRaises(InvalidStatus) as raised:
                async with connect(get_uri(server)):
                    self.fail("did not raise")
            self.assertEqual(
                str(raised.exception),
                "server rejected WebSocket connection: HTTP 500",
            )

    async def test_process_response_returns_none(self):
        """Server runs process_response but keeps the handshake response."""

        def process_response(ws, request, response):
            self.assertIsInstance(request, Request)
            self.assertIsInstance(response, Response)
            ws.process_response_ran = True

        async with serve(*args, process_response=process_response) as server:
            async with connect(get_uri(server)) as client:
                await self.assertEval(client, "ws.process_response_ran", "True")

    async def test_async_process_response_returns_none(self):
        """Server runs async process_response but keeps the handshake response."""

        async def process_response(ws, request, response):
            self.assertIsInstance(request, Request)
            self.assertIsInstance(response, Response)
            ws.process_response_ran = True

        async with serve(*args, process_response=process_response) as server:
            async with connect(get_uri(server)) as client:
                await self.assertEval(client, "ws.process_response_ran", "True")

    async def test_process_response_modifies_response(self):
        """Server runs process_response and modifies the handshake response."""

        def process_response(ws, request, response):
            response.headers["X-ProcessResponse"] = "OK"

        async with serve(*args, process_response=process_response) as server:
            async with connect(get_uri(server)) as client:
                self.assertEqual(client.response.headers["X-ProcessResponse"], "OK")

    async def test_async_process_response_modifies_response(self):
        """Server runs async process_response and modifies the handshake response."""

        async def process_response(ws, request, response):
            response.headers["X-ProcessResponse"] = "OK"

        async with serve(*args, process_response=process_response) as server:
            async with connect(get_uri(server)) as client:
                self.assertEqual(client.response.headers["X-ProcessResponse"], "OK")

    async def test_process_response_replaces_response(self):
        """Server runs process_response and replaces the handshake response."""

        def process_response(ws, request, response):
            headers = response.headers.copy()
            headers["X-ProcessResponse"] = "OK"
            return dataclasses.replace(response, headers=headers)

        async with serve(*args, process_response=process_response) as server:
            async with connect(get_uri(server)) as client:
                self.assertEqual(client.response.headers["X-ProcessResponse"], "OK")

    async def test_async_process_response_replaces_response(self):
        """Server runs async process_response and replaces the handshake response."""

        async def process_response(ws, request, response):
            headers = response.headers.copy()
            headers["X-ProcessResponse"] = "OK"
            return dataclasses.replace(response, headers=headers)

        async with serve(*args, process_response=process_response) as server:
            async with connect(get_uri(server)) as client:
                self.assertEqual(client.response.headers["X-ProcessResponse"], "OK")

    async def test_process_response_raises_exception(self):
        """Server returns an error if process_response raises an exception."""

        def process_response(ws, request, response):
            raise RuntimeError

        async with serve(*args, process_response=process_response) as server:
            with self.assertRaises(InvalidStatus) as raised:
                async with connect(get_uri(server)):
                    self.fail("did not raise")
            self.assertEqual(
                str(raised.exception),
                "server rejected WebSocket connection: HTTP 500",
            )

    async def test_async_process_response_raises_exception(self):
        """Server returns an error if async process_response raises an exception."""

        async def process_response(ws, request, response):
            raise RuntimeError

        async with serve(*args, process_response=process_response) as server:
            with self.assertRaises(InvalidStatus) as raised:
                async with connect(get_uri(server)):
                    self.fail("did not raise")
            self.assertEqual(
                str(raised.exception),
                "server rejected WebSocket connection: HTTP 500",
            )

    async def test_override_server(self):
        """Server can override Server header with server_header."""
        async with serve(*args, server_header="Neo") as server:
            async with connect(get_uri(server)) as client:
                await self.assertEval(client, "ws.response.headers['Server']", "Neo")

    async def test_remove_server(self):
        """Server can remove Server header with server_header."""
        async with serve(*args, server_header=None) as server:
            async with connect(get_uri(server)) as client:
                await self.assertEval(
                    client, "'Server' in ws.response.headers", "False"
                )

    async def test_compression_is_enabled(self):
        """Server enables compression by default."""
        async with serve(*args) as server:
            async with connect(get_uri(server)) as client:
                await self.assertEval(
                    client,
                    "[type(ext).__name__ for ext in ws.protocol.extensions]",
                    "['PerMessageDeflate']",
                )

    async def test_disable_compression(self):
        """Server disables compression."""
        async with serve(*args, compression=None) as server:
            async with connect(get_uri(server)) as client:
                await self.assertEval(client, "ws.protocol.extensions", "[]")

    async def test_keepalive_is_enabled(self):
        """Server enables keepalive and measures latency."""
        async with serve(*args, ping_interval=MS) as server:
            async with connect(get_uri(server)) as client:
                await client.send("ws.latency")
                latency = eval(await client.recv())
                self.assertEqual(latency, 0)
                await asyncio.sleep(2 * MS)
                await client.send("ws.latency")
                latency = eval(await client.recv())
                self.assertGreater(latency, 0)

    async def test_disable_keepalive(self):
        """Server disables keepalive."""
        async with serve(*args, ping_interval=None) as server:
            async with connect(get_uri(server)) as client:
                await asyncio.sleep(2 * MS)
                await client.send("ws.latency")
                latency = eval(await client.recv())
                self.assertEqual(latency, 0)

    async def test_logger(self):
        """Server accepts a logger argument."""
        logger = logging.getLogger("test")
        async with serve(*args, logger=logger) as server:
            self.assertEqual(server.logger.name, logger.name)

    async def test_custom_connection_factory(self):
        """Server runs ServerConnection factory provided in create_connection."""

        def create_connection(*args, **kwargs):
            server = ServerConnection(*args, **kwargs)
            server.create_connection_ran = True
            return server

        async with serve(*args, create_connection=create_connection) as server:
            async with connect(get_uri(server)) as client:
                await self.assertEval(client, "ws.create_connection_ran", "True")

    async def test_connections(self):
        """Server provides a connections property."""
        async with serve(*args) as server:
            self.assertEqual(server.connections, set())
            async with connect(get_uri(server)) as client:
                self.assertEqual(len(server.connections), 1)
                ws_id = str(next(iter(server.connections)).id)
                await self.assertEval(client, "ws.id", ws_id)
            self.assertEqual(server.connections, set())

    async def test_handshake_fails(self):
        """Server receives connection from client but the handshake fails."""

        def remove_key_header(self, request):
            del request.headers["Sec-WebSocket-Key"]

        async with serve(*args, process_request=remove_key_header) as server:
            with self.assertRaises(InvalidStatus) as raised:
                async with connect(get_uri(server)):
                    self.fail("did not raise")
            self.assertEqual(
                str(raised.exception),
                "server rejected WebSocket connection: HTTP 400",
            )

    async def test_timeout_during_handshake(self):
        """Server times out before receiving handshake request from client."""
        async with serve(*args, open_timeout=MS) as server:
            reader, writer = await asyncio.open_connection(*get_host_port(server))
            try:
                self.assertEqual(await reader.read(4096), b"")
            finally:
                writer.close()

    async def test_connection_closed_during_handshake(self):
        """Server reads EOF before receiving handshake request from client."""
        async with serve(*args) as server:
            _reader, writer = await asyncio.open_connection(*get_host_port(server))
            writer.close()

    async def test_junk_handshake(self):
        """Server closes the connection when receiving non-HTTP request from client."""
        with self.assertLogs("websockets", logging.ERROR) as logs:
            async with serve(*args) as server:
                reader, writer = await asyncio.open_connection(*get_host_port(server))
                writer.write(b"HELO relay.invalid\r\n")
                try:
                    # Wait for the server to close the connection.
                    self.assertEqual(await reader.read(4096), b"")
                finally:
                    writer.close()

        self.assertEqual(
            [record.getMessage() for record in logs.records],
            ["opening handshake failed"],
        )
        self.assertEqual(
            [str(record.exc_info[1]) for record in logs.records],
            ["invalid HTTP request line: HELO relay.invalid"],
        )

    async def test_close_server_rejects_connecting_connections(self):
        """Server rejects connecting connections with HTTP 503 when closing."""

        async def process_request(ws, _request):
            while ws.server.is_serving():
                await asyncio.sleep(0)  # pragma: no cover

        async with serve(*args, process_request=process_request) as server:
            asyncio.get_running_loop().call_later(MS, server.close)
            with self.assertRaises(InvalidStatus) as raised:
                async with connect(get_uri(server)):
                    self.fail("did not raise")
            self.assertEqual(
                str(raised.exception),
                "server rejected WebSocket connection: HTTP 503",
            )

    async def test_close_server_closes_open_connections(self):
        """Server closes open connections with close code 1001 when closing."""
        async with serve(*args) as server:
            async with connect(get_uri(server)) as client:
                server.close()
                with self.assertRaises(ConnectionClosedOK) as raised:
                    await client.recv()
                self.assertEqual(
                    str(raised.exception),
                    "received 1001 (going away); then sent 1001 (going away)",
                )

    async def test_close_server_keeps_connections_open(self):
        """Server waits for client to close open connections when closing."""
        async with serve(*args) as server:
            async with connect(get_uri(server)) as client:
                server.close(close_connections=False)

                # Server cannot receive new connections.
                await asyncio.sleep(0)
                self.assertFalse(server.sockets)

                # The server waits for the client to close the connection.
                with self.assertRaises(TimeoutError):
                    async with asyncio_timeout(MS):
                        await server.wait_closed()

                # Once the client closes the connection, the server terminates.
                await client.close()
                async with asyncio_timeout(MS):
                    await server.wait_closed()

    async def test_close_server_keeps_handlers_running(self):
        """Server waits for connection handlers to terminate."""
        async with serve(*args) as server:
            async with connect(get_uri(server) + "/delay") as client:
                # Delay termination of connection handler.
                await client.send(str(3 * MS))

                server.close()

                # The server waits for the connection handler to terminate.
                with self.assertRaises(TimeoutError):
                    async with asyncio_timeout(2 * MS):
                        await server.wait_closed()

                async with asyncio_timeout(3 * MS):
                    await server.wait_closed()


SSL_OBJECT = "ws.transport.get_extra_info('ssl_object')"


class SecureServerTests(EvalShellMixin, unittest.IsolatedAsyncioTestCase):
    async def test_connection(self):
        """Server receives secure connection from client."""
        async with serve(*args, ssl=SERVER_CONTEXT) as server:
            async with connect(get_uri(server), ssl=CLIENT_CONTEXT) as client:
                await self.assertEval(client, "ws.protocol.state.name", "OPEN")
                await self.assertEval(client, SSL_OBJECT + ".version()[:3]", "TLS")

    async def test_timeout_during_tls_handshake(self):
        """Server times out before receiving TLS handshake request from client."""
        async with serve(*args, ssl=SERVER_CONTEXT, open_timeout=MS) as server:
            reader, writer = await asyncio.open_connection(*get_host_port(server))
            try:
                self.assertEqual(await reader.read(4096), b"")
            finally:
                writer.close()

    async def test_connection_closed_during_tls_handshake(self):
        """Server reads EOF before receiving TLS handshake request from client."""
        async with serve(*args, ssl=SERVER_CONTEXT) as server:
            _reader, writer = await asyncio.open_connection(*get_host_port(server))
            writer.close()


@unittest.skipUnless(hasattr(socket, "AF_UNIX"), "this test requires Unix sockets")
class UnixServerTests(EvalShellMixin, unittest.IsolatedAsyncioTestCase):
    async def test_connection(self):
        """Server receives connection from client over a Unix socket."""
        with temp_unix_socket_path() as path:
            async with unix_serve(handler, path):
                async with unix_connect(path) as client:
                    await self.assertEval(client, "ws.protocol.state.name", "OPEN")


@unittest.skipUnless(hasattr(socket, "AF_UNIX"), "this test requires Unix sockets")
class SecureUnixServerTests(EvalShellMixin, unittest.IsolatedAsyncioTestCase):
    async def test_connection(self):
        """Server receives secure connection from client over a Unix socket."""
        with temp_unix_socket_path() as path:
            async with unix_serve(handler, path, ssl=SERVER_CONTEXT):
                async with unix_connect(path, ssl=CLIENT_CONTEXT) as client:
                    await self.assertEval(client, "ws.protocol.state.name", "OPEN")
                    await self.assertEval(client, SSL_OBJECT + ".version()[:3]", "TLS")


class ServerUsageErrorsTests(unittest.IsolatedAsyncioTestCase):
    async def test_unix_without_path_or_sock(self):
        """Unix server requires path when sock isn't provided."""
        with self.assertRaises(ValueError) as raised:
            await unix_serve(handler)
        self.assertEqual(
            str(raised.exception),
            "path was not specified, and no sock specified",
        )

    async def test_unix_with_path_and_sock(self):
        """Unix server rejects path when sock is provided."""
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.addCleanup(sock.close)
        with self.assertRaises(ValueError) as raised:
            await unix_serve(handler, path="/", sock=sock)
        self.assertEqual(
            str(raised.exception),
            "path and sock can not be specified at the same time",
        )

    async def test_invalid_subprotocol(self):
        """Server rejects single value of subprotocols."""
        with self.assertRaises(TypeError) as raised:
            await serve(*args, subprotocols="chat")
        self.assertEqual(
            str(raised.exception),
            "subprotocols must be a list, not a str",
        )

    async def test_unsupported_compression(self):
        """Server rejects incorrect value of compression."""
        with self.assertRaises(ValueError) as raised:
            await serve(*args, compression=False)
        self.assertEqual(
            str(raised.exception),
            "unsupported compression: False",
        )


class BasicAuthTests(EvalShellMixin, unittest.IsolatedAsyncioTestCase):
    async def test_valid_authorization(self):
        """basic_auth authenticates client with HTTP Basic Authentication."""
        async with serve(
            *args,
            process_request=basic_auth(credentials=("hello", "iloveyou")),
        ) as server:
            async with connect(
                get_uri(server),
                additional_headers={"Authorization": "Basic aGVsbG86aWxvdmV5b3U="},
            ) as client:
                await self.assertEval(client, "ws.username", "hello")

    async def test_missing_authorization(self):
        """basic_auth rejects client without credentials."""
        async with serve(
            *args,
            process_request=basic_auth(credentials=("hello", "iloveyou")),
        ) as server:
            with self.assertRaises(InvalidStatus) as raised:
                async with connect(get_uri(server)):
                    self.fail("did not raise")
            self.assertEqual(
                str(raised.exception),
                "server rejected WebSocket connection: HTTP 401",
            )

    async def test_unsupported_authorization(self):
        """basic_auth rejects client with unsupported credentials."""
        async with serve(
            *args,
            process_request=basic_auth(credentials=("hello", "iloveyou")),
        ) as server:
            with self.assertRaises(InvalidStatus) as raised:
                async with connect(
                    get_uri(server),
                    additional_headers={"Authorization": "Negotiate ..."},
                ):
                    self.fail("did not raise")
            self.assertEqual(
                str(raised.exception),
                "server rejected WebSocket connection: HTTP 401",
            )

    async def test_authorization_with_unknown_username(self):
        """basic_auth rejects client with unknown username."""
        async with serve(
            *args,
            process_request=basic_auth(credentials=("hello", "iloveyou")),
        ) as server:
            with self.assertRaises(InvalidStatus) as raised:
                async with connect(
                    get_uri(server),
                    additional_headers={"Authorization": "Basic YnllOnlvdWxvdmVtZQ=="},
                ):
                    self.fail("did not raise")
            self.assertEqual(
                str(raised.exception),
                "server rejected WebSocket connection: HTTP 401",
            )

    async def test_authorization_with_incorrect_password(self):
        """basic_auth rejects client with incorrect password."""
        async with serve(
            *args,
            process_request=basic_auth(credentials=("hello", "changeme")),
        ) as server:
            with self.assertRaises(InvalidStatus) as raised:
                async with connect(
                    get_uri(server),
                    additional_headers={"Authorization": "Basic aGVsbG86aWxvdmV5b3U="},
                ):
                    self.fail("did not raise")
            self.assertEqual(
                str(raised.exception),
                "server rejected WebSocket connection: HTTP 401",
            )

    async def test_list_of_credentials(self):
        """basic_auth accepts a list of hard coded credentials."""
        async with serve(
            *args,
            process_request=basic_auth(
                credentials=[
                    ("hello", "iloveyou"),
                    ("bye", "youloveme"),
                ]
            ),
        ) as server:
            async with connect(
                get_uri(server),
                additional_headers={"Authorization": "Basic YnllOnlvdWxvdmVtZQ=="},
            ) as client:
                await self.assertEval(client, "ws.username", "bye")

    async def test_check_credentials_function(self):
        """basic_auth accepts a check_credentials function."""

        def check_credentials(username, password):
            return hmac.compare_digest(password, "iloveyou")

        async with serve(
            *args,
            process_request=basic_auth(check_credentials=check_credentials),
        ) as server:
            async with connect(
                get_uri(server),
                additional_headers={"Authorization": "Basic aGVsbG86aWxvdmV5b3U="},
            ) as client:
                await self.assertEval(client, "ws.username", "hello")

    async def test_check_credentials_coroutine(self):
        """basic_auth accepts a check_credentials coroutine."""

        async def check_credentials(username, password):
            return hmac.compare_digest(password, "iloveyou")

        async with serve(
            *args,
            process_request=basic_auth(check_credentials=check_credentials),
        ) as server:
            async with connect(
                get_uri(server),
                additional_headers={"Authorization": "Basic aGVsbG86aWxvdmV5b3U="},
            ) as client:
                await self.assertEval(client, "ws.username", "hello")

    async def test_without_credentials_or_check_credentials(self):
        """basic_auth requires either credentials or check_credentials."""
        with self.assertRaises(ValueError) as raised:
            basic_auth()
        self.assertEqual(
            str(raised.exception),
            "provide either credentials or check_credentials",
        )

    async def test_with_credentials_and_check_credentials(self):
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

    async def test_bad_credentials(self):
        """basic_auth receives an unsupported credentials argument."""
        with self.assertRaises(TypeError) as raised:
            basic_auth(credentials=42)
        self.assertEqual(
            str(raised.exception),
            "invalid credentials argument: 42",
        )

    async def test_bad_list_of_credentials(self):
        """basic_auth receives an unsupported credentials argument."""
        with self.assertRaises(TypeError) as raised:
            basic_auth(credentials=[42])
        self.assertEqual(
            str(raised.exception),
            "invalid credentials argument: [42]",
        )
