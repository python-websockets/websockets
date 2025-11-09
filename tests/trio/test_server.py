import dataclasses
import hmac
import http
import logging

import trio

from websockets.exceptions import (
    ConnectionClosedError,
    ConnectionClosedOK,
    InvalidStatus,
    NegotiationError,
)
from websockets.http11 import Request, Response
from websockets.trio.client import connect
from websockets.trio.server import *

from ..utils import (
    CLIENT_CONTEXT,
    MS,
    SERVER_CONTEXT,
)
from .server import (
    EvalShellMixin,
    get_host_port,
    get_uri,
    handler,
    run_server,
)
from .utils import IsolatedTrioTestCase


class ServerTests(EvalShellMixin, IsolatedTrioTestCase):
    async def test_connection(self):
        """Server receives connection from client and the handshake succeeds."""
        async with run_server() as server:
            async with connect(get_uri(server)) as client:
                await self.assertEval(client, "ws.protocol.state.name", "OPEN")

    async def test_connection_handler_returns(self):
        """Connection handler returns."""
        async with run_server() as server:
            async with connect(get_uri(server) + "/no-op") as client:
                with self.assertRaises(ConnectionClosedOK) as raised:
                    await client.recv()
                self.assertEqual(
                    str(raised.exception),
                    "received 1000 (OK); then sent 1000 (OK)",
                )

    async def test_connection_handler_raises_exception(self):
        """Connection handler raises an exception."""
        async with run_server() as server:
            async with connect(get_uri(server) + "/crash") as client:
                with self.assertRaises(ConnectionClosedError) as raised:
                    await client.recv()
                self.assertEqual(
                    str(raised.exception),
                    "received 1011 (internal error); then sent 1011 (internal error)",
                )

    async def test_existing_listeners(self):
        """Server receives connection using pre-existing listeners."""
        listeners = await trio.open_tcp_listeners(0, host="localhost")
        host, port = get_host_port(listeners)
        async with run_server(port=None, host=None, listeners=listeners):
            async with connect(f"ws://{host}:{port}/") as client:  # type: ignore
                await self.assertEval(client, "ws.protocol.state.name", "OPEN")

    async def test_select_subprotocol(self):
        """Server selects a subprotocol with the select_subprotocol callable."""

        def select_subprotocol(ws, subprotocols):
            ws.select_subprotocol_ran = True
            assert "chat" in subprotocols
            return "chat"

        async with run_server(
            subprotocols=["chat"], select_subprotocol=select_subprotocol
        ) as server:
            async with connect(get_uri(server), subprotocols=["chat"]) as client:
                await self.assertEval(client, "ws.select_subprotocol_ran", "True")
                await self.assertEval(client, "ws.subprotocol", "chat")

    async def test_select_subprotocol_rejects_handshake(self):
        """Server rejects handshake if select_subprotocol raises NegotiationError."""

        def select_subprotocol(ws, subprotocols):
            raise NegotiationError

        async with run_server(select_subprotocol=select_subprotocol) as server:
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

        async with run_server(select_subprotocol=select_subprotocol) as server:
            with self.assertRaises(InvalidStatus) as raised:
                async with connect(get_uri(server)):
                    self.fail("did not raise")
            self.assertEqual(
                str(raised.exception),
                "server rejected WebSocket connection: HTTP 500",
            )

    async def test_compression_is_enabled(self):
        """Server enables compression by default."""
        async with run_server() as server:
            async with connect(get_uri(server)) as client:
                await self.assertEval(
                    client,
                    "[type(ext).__name__ for ext in ws.protocol.extensions]",
                    "['PerMessageDeflate']",
                )

    async def test_disable_compression(self):
        """Server disables compression."""
        async with run_server(compression=None) as server:
            async with connect(get_uri(server)) as client:
                await self.assertEval(client, "ws.protocol.extensions", "[]")

    async def test_process_request_returns_none(self):
        """Server runs process_request and continues the handshake."""

        def process_request(ws, request):
            self.assertIsInstance(request, Request)
            ws.process_request_ran = True

        async with run_server(process_request=process_request) as server:
            async with connect(get_uri(server)) as client:
                await self.assertEval(client, "ws.process_request_ran", "True")

    async def test_async_process_request_returns_none(self):
        """Server runs async process_request and continues the handshake."""

        async def process_request(ws, request):
            self.assertIsInstance(request, Request)
            ws.process_request_ran = True

        async with run_server(process_request=process_request) as server:
            async with connect(get_uri(server)) as client:
                await self.assertEval(client, "ws.process_request_ran", "True")

    async def test_process_request_returns_response(self):
        """Server aborts handshake if process_request returns a response."""

        def process_request(ws, request):
            return ws.respond(http.HTTPStatus.FORBIDDEN, "Forbidden")

        async def handler(ws):
            self.fail("handler must not run")

        with self.assertNoLogs("websockets", logging.ERROR):
            async with run_server(process_request=process_request) as server:
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

        with self.assertNoLogs("websockets", logging.ERROR):
            async with run_server(process_request=process_request) as server:
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
            raise RuntimeError("BOOM")

        with self.assertLogs("websockets", logging.ERROR) as logs:
            async with run_server(process_request=process_request) as server:
                with self.assertRaises(InvalidStatus) as raised:
                    async with connect(get_uri(server)):
                        self.fail("did not raise")
                self.assertEqual(
                    str(raised.exception),
                    "server rejected WebSocket connection: HTTP 500",
                )
        self.assertEqual(
            [record.getMessage() for record in logs.records],
            ["opening handshake failed"],
        )
        self.assertEqual(
            [str(record.exc_info[1]) for record in logs.records],
            ["BOOM"],
        )

    async def test_async_process_request_raises_exception(self):
        """Server returns an error if async process_request raises an exception."""

        async def process_request(ws, request):
            raise RuntimeError("BOOM")

        with self.assertLogs("websockets", logging.ERROR) as logs:
            async with run_server(process_request=process_request) as server:
                with self.assertRaises(InvalidStatus) as raised:
                    async with connect(get_uri(server)):
                        self.fail("did not raise")
                self.assertEqual(
                    str(raised.exception),
                    "server rejected WebSocket connection: HTTP 500",
                )
        self.assertEqual(
            [record.getMessage() for record in logs.records],
            ["opening handshake failed"],
        )
        self.assertEqual(
            [str(record.exc_info[1]) for record in logs.records],
            ["BOOM"],
        )

    async def test_process_response_returns_none(self):
        """Server runs process_response but keeps the handshake response."""

        def process_response(ws, request, response):
            self.assertIsInstance(request, Request)
            self.assertIsInstance(response, Response)
            ws.process_response_ran = True

        async with run_server(process_response=process_response) as server:
            async with connect(get_uri(server)) as client:
                await self.assertEval(client, "ws.process_response_ran", "True")

    async def test_async_process_response_returns_none(self):
        """Server runs async process_response but keeps the handshake response."""

        async def process_response(ws, request, response):
            self.assertIsInstance(request, Request)
            self.assertIsInstance(response, Response)
            ws.process_response_ran = True

        async with run_server(process_response=process_response) as server:
            async with connect(get_uri(server)) as client:
                await self.assertEval(client, "ws.process_response_ran", "True")

    async def test_process_response_modifies_response(self):
        """Server runs process_response and modifies the handshake response."""

        def process_response(ws, request, response):
            response.headers["X-ProcessResponse"] = "OK"

        async with run_server(process_response=process_response) as server:
            async with connect(get_uri(server)) as client:
                self.assertEqual(client.response.headers["X-ProcessResponse"], "OK")

    async def test_async_process_response_modifies_response(self):
        """Server runs async process_response and modifies the handshake response."""

        async def process_response(ws, request, response):
            response.headers["X-ProcessResponse"] = "OK"

        async with run_server(process_response=process_response) as server:
            async with connect(get_uri(server)) as client:
                self.assertEqual(client.response.headers["X-ProcessResponse"], "OK")

    async def test_process_response_replaces_response(self):
        """Server runs process_response and replaces the handshake response."""

        def process_response(ws, request, response):
            headers = response.headers.copy()
            headers["X-ProcessResponse"] = "OK"
            return dataclasses.replace(response, headers=headers)

        async with run_server(process_response=process_response) as server:
            async with connect(get_uri(server)) as client:
                self.assertEqual(client.response.headers["X-ProcessResponse"], "OK")

    async def test_async_process_response_replaces_response(self):
        """Server runs async process_response and replaces the handshake response."""

        async def process_response(ws, request, response):
            headers = response.headers.copy()
            headers["X-ProcessResponse"] = "OK"
            return dataclasses.replace(response, headers=headers)

        async with run_server(process_response=process_response) as server:
            async with connect(get_uri(server)) as client:
                self.assertEqual(client.response.headers["X-ProcessResponse"], "OK")

    async def test_process_response_raises_exception(self):
        """Server returns an error if process_response raises an exception."""

        def process_response(ws, request, response):
            raise RuntimeError("BOOM")

        with self.assertLogs("websockets", logging.ERROR) as logs:
            async with run_server(process_response=process_response) as server:
                with self.assertRaises(InvalidStatus) as raised:
                    async with connect(get_uri(server)):
                        self.fail("did not raise")
                self.assertEqual(
                    str(raised.exception),
                    "server rejected WebSocket connection: HTTP 500",
                )
        self.assertEqual(
            [record.getMessage() for record in logs.records],
            ["opening handshake failed"],
        )
        self.assertEqual(
            [str(record.exc_info[1]) for record in logs.records],
            ["BOOM"],
        )

    async def test_async_process_response_raises_exception(self):
        """Server returns an error if async process_response raises an exception."""

        async def process_response(ws, request, response):
            raise RuntimeError("BOOM")

        with self.assertLogs("websockets", logging.ERROR) as logs:
            async with run_server(process_response=process_response) as server:
                with self.assertRaises(InvalidStatus) as raised:
                    async with connect(get_uri(server)):
                        self.fail("did not raise")
                self.assertEqual(
                    str(raised.exception),
                    "server rejected WebSocket connection: HTTP 500",
                )
        self.assertEqual(
            [record.getMessage() for record in logs.records],
            ["opening handshake failed"],
        )
        self.assertEqual(
            [str(record.exc_info[1]) for record in logs.records],
            ["BOOM"],
        )

    async def test_override_server(self):
        """Server can override Server header with server_header."""
        async with run_server(server_header="Neo") as server:
            async with connect(get_uri(server)) as client:
                await self.assertEval(client, "ws.response.headers['Server']", "Neo")

    async def test_remove_server(self):
        """Server can remove Server header with server_header."""
        async with run_server(server_header=None) as server:
            async with connect(get_uri(server)) as client:
                await self.assertEval(
                    client, "'Server' in ws.response.headers", "False"
                )

    async def test_keepalive_is_enabled(self):
        """Server enables keepalive and measures latency."""
        async with run_server(ping_interval=MS) as server:
            async with connect(get_uri(server)) as client:
                await client.send("ws.latency")
                latency = eval(await client.recv())
                self.assertEqual(latency, 0)
                await trio.sleep(2 * MS)
                await client.send("ws.latency")
                latency = eval(await client.recv())
                self.assertGreater(latency, 0)

    async def test_disable_keepalive(self):
        """Server disables keepalive."""
        async with run_server(ping_interval=None) as server:
            async with connect(get_uri(server)) as client:
                await trio.sleep(2 * MS)
                await client.send("ws.latency")
                latency = eval(await client.recv())
                self.assertEqual(latency, 0)

    async def test_logger(self):
        """Server accepts a logger argument."""
        logger = logging.getLogger("test")
        async with run_server(logger=logger) as server:
            self.assertEqual(server.logger.name, logger.name)

    async def test_custom_connection_factory(self):
        """Server runs ServerConnection factory provided in create_connection."""

        def create_connection(*args, **kwargs):
            server = ServerConnection(*args, **kwargs)
            server.create_connection_ran = True
            return server

        async with run_server(create_connection=create_connection) as server:
            async with connect(get_uri(server)) as client:
                await self.assertEval(client, "ws.create_connection_ran", "True")

    async def test_connections(self):
        """Server provides a connections property."""
        async with run_server() as server:
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

        async with run_server(process_request=remove_key_header) as server:
            with self.assertRaises(InvalidStatus) as raised:
                async with connect(get_uri(server)):
                    self.fail("did not raise")
            self.assertEqual(
                str(raised.exception),
                "server rejected WebSocket connection: HTTP 400",
            )

    async def test_timeout_during_handshake(self):
        """Server times out before receiving handshake request from client."""
        async with run_server(open_timeout=MS) as server:
            stream = await trio.open_tcp_stream(*get_host_port(server.listeners))
            try:
                self.assertEqual(await stream.receive_some(4096), b"")
            finally:
                await stream.aclose()

    async def test_connection_closed_during_handshake(self):
        """Server reads EOF before receiving handshake request from client."""
        async with run_server() as server:
            stream = await trio.open_tcp_stream(*get_host_port(server.listeners))
            await stream.aclose()

    async def test_junk_handshake(self):
        """Server closes the connection when receiving non-HTTP request from client."""
        with self.assertLogs("websockets", logging.ERROR) as logs:
            async with run_server() as server:
                stream = await trio.open_tcp_stream(*get_host_port(server.listeners))
                await stream.send_all(b"HELO relay.invalid\r\n")
                try:
                    # Wait for the server to close the connection.
                    self.assertEqual(await stream.receive_some(4096), b"")
                finally:
                    await stream.aclose()

        self.assertEqual(
            [record.getMessage() for record in logs.records],
            ["opening handshake failed"],
        )
        self.assertEqual(
            [str(record.exc_info[1]) for record in logs.records],
            ["did not receive a valid HTTP request"],
        )
        self.assertEqual(
            [str(record.exc_info[1].__cause__) for record in logs.records],
            ["invalid HTTP request line: HELO relay.invalid"],
        )

    async def test_close_server_rejects_connecting_connections(self):
        """Server rejects connecting connections with HTTP 503 when closing."""

        async def process_request(ws, _request):
            while not ws.server.closing:
                await trio.sleep(0)  # pragma: no cover

        async with run_server(process_request=process_request) as server:

            async def close_server(server):
                await trio.sleep(MS)
                await server.aclose()

            self.nursery.start_soon(close_server, server)

            with self.assertRaises(InvalidStatus) as raised:
                async with connect(get_uri(server)):
                    self.fail("did not raise")

            self.assertEqual(
                str(raised.exception),
                "server rejected WebSocket connection: HTTP 503",
            )

    async def test_close_server_closes_open_connections(self):
        """Server closes open connections with close code 1001 when closing."""
        async with run_server() as server:
            async with connect(get_uri(server)) as client:
                await server.aclose()
                with self.assertRaises(ConnectionClosedOK) as raised:
                    await client.recv()
                self.assertEqual(
                    str(raised.exception),
                    "received 1001 (going away); then sent 1001 (going away)",
                )

    async def test_close_server_closes_open_connections_with_code_and_reason(self):
        """Server closes open connections with custom code and reason when closing."""
        async with run_server() as server:
            async with connect(get_uri(server)) as client:
                await server.aclose(code=1012, reason="restarting")
                with self.assertRaises(ConnectionClosedError) as raised:
                    await client.recv()
                self.assertEqual(
                    str(raised.exception),
                    "received 1012 (service restart) restarting; "
                    "then sent 1012 (service restart) restarting",
                )

    async def test_close_server_keeps_connections_open(self):
        """Server waits for client to close open connections when closing."""

        async with run_server() as server:
            server_closed = trio.Event()

            async def close_server():
                await server.aclose(close_connections=False)
                server_closed.set()

            async with connect(get_uri(server)) as client:
                self.nursery.start_soon(close_server)

                # Server cannot receive new connections.
                with self.assertRaises(OSError):
                    async with connect(get_uri(server)):
                        self.fail("did not raise")

                # The server waits for the client to close the connection.
                with self.assertRaises(trio.TooSlowError):
                    with trio.fail_after(MS):
                        await server_closed.wait()

                # Once the client closes the connection, the server terminates.
                await client.aclose()
                with trio.fail_after(MS):
                    await server_closed.wait()

    async def test_close_server_keeps_handlers_running(self):
        """Server waits for connection handlers to terminate."""
        async with run_server() as server:
            server_closed = trio.Event()

            async def close_server():
                await server.aclose(close_connections=False)
                server_closed.set()

            async with connect(get_uri(server) + "/delay") as client:
                # Delay termination of connection handler.
                await client.send(str(3 * MS))

                self.nursery.start_soon(close_server)

                # The server waits for the connection handler to terminate.
                with self.assertRaises(trio.TooSlowError):
                    with trio.fail_after(2 * MS):
                        await server_closed.wait()

                # Set a large timeout here, else the test becomes flaky.
                with trio.fail_after(5 * MS):
                    await server_closed.wait()


SSL_OBJECT = "ws.stream._ssl_object"


class SecureServerTests(EvalShellMixin, IsolatedTrioTestCase):
    async def test_connection(self):
        """Server receives secure connection from client."""
        async with run_server(ssl=SERVER_CONTEXT) as server:
            async with connect(
                get_uri(server, secure=True), ssl=CLIENT_CONTEXT
            ) as client:
                await self.assertEval(client, "ws.protocol.state.name", "OPEN")
                await self.assertEval(client, f"{SSL_OBJECT}.version()[:3]", "TLS")

    async def test_timeout_during_tls_handshake(self):
        """Server times out before receiving TLS handshake request from client."""
        async with run_server(ssl=SERVER_CONTEXT, open_timeout=MS) as server:
            stream = await trio.open_tcp_stream(*get_host_port(server.listeners))
            try:
                self.assertEqual(await stream.receive_some(4096), b"")
            finally:
                await stream.aclose()

    async def test_connection_closed_during_tls_handshake(self):
        """Server reads EOF before receiving TLS handshake request from client."""
        async with run_server(ssl=SERVER_CONTEXT) as server:
            stream = await trio.open_tcp_stream(*get_host_port(server.listeners))
            await stream.aclose()


class ServerUsageErrorsTests(IsolatedTrioTestCase):
    async def test_missing_port(self):
        """Server requires port."""
        with self.assertRaises(ValueError) as raised:
            await serve(handler, None)
        self.assertEqual(
            str(raised.exception),
            "port is required when listeners is not provided",
        )

    async def test_port_and_listeners(self):
        """Server rejects port when listeners is provided."""
        listeners = await trio.open_tcp_listeners(0)
        try:
            with self.assertRaises(ValueError) as raised:
                await serve(handler, port=0, listeners=listeners)
            self.assertEqual(
                str(raised.exception),
                "port is incompatible with listeners",
            )
        finally:
            for listener in listeners:
                await listener.aclose()

    async def test_host_and_listeners(self):
        """Server rejects host when listeners is provided."""
        listeners = await trio.open_tcp_listeners(0)
        try:
            with self.assertRaises(ValueError) as raised:
                await serve(handler, host="localhost", listeners=listeners)
            self.assertEqual(
                str(raised.exception),
                "host is incompatible with listeners",
            )
        finally:
            for listener in listeners:
                await listener.aclose()

    async def test_backlog_and_listeners(self):
        """Server rejects backlog when listeners is provided."""
        listeners = await trio.open_tcp_listeners(0)
        try:
            with self.assertRaises(ValueError) as raised:
                await serve(handler, backlog=65535, listeners=listeners)
            self.assertEqual(
                str(raised.exception),
                "backlog is incompatible with listeners",
            )
        finally:
            for listener in listeners:
                await listener.aclose()

    async def test_invalid_subprotocol(self):
        """Server rejects single value of subprotocols."""
        with self.assertRaises(TypeError) as raised:
            await serve(handler, subprotocols="chat")
        self.assertEqual(
            str(raised.exception),
            "subprotocols must be a list, not a str",
        )

    async def test_unsupported_compression(self):
        """Server rejects incorrect value of compression."""
        with self.assertRaises(ValueError) as raised:
            await serve(handler, compression=False)
        self.assertEqual(
            str(raised.exception),
            "unsupported compression: False",
        )


class BasicAuthTests(EvalShellMixin, IsolatedTrioTestCase):
    async def test_valid_authorization(self):
        """basic_auth authenticates client with HTTP Basic Authentication."""
        async with run_server(
            process_request=basic_auth(credentials=("hello", "iloveyou")),
        ) as server:
            async with connect(
                get_uri(server),
                additional_headers={"Authorization": "Basic aGVsbG86aWxvdmV5b3U="},
            ) as client:
                await self.assertEval(client, "ws.username", "hello")

    async def test_missing_authorization(self):
        """basic_auth rejects client without credentials."""
        async with run_server(
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
        async with run_server(
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
        async with run_server(
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
        async with run_server(
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
        async with run_server(
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

        async with run_server(
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

        async with run_server(
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
