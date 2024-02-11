import asyncio
import dataclasses
import http
import logging
import socket
import unittest

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
from .client import run_client, run_unix_client
from .server import (
    EvalShellMixin,
    crash,
    do_nothing,
    eval_shell,
    get_server_host_port,
    run_server,
    run_unix_server,
)


class ServerTests(EvalShellMixin, unittest.IsolatedAsyncioTestCase):
    async def test_connection(self):
        """Server receives connection from client and the handshake succeeds."""
        async with run_server() as server:
            async with run_client(server) as client:
                await self.assertEval(client, "ws.protocol.state.name", "OPEN")

    async def test_connection_handler_returns(self):
        """Connection handler returns."""
        async with run_server(do_nothing) as server:
            async with run_client(server) as client:
                with self.assertRaises(ConnectionClosedOK) as raised:
                    await client.recv()
                self.assertEqual(
                    str(raised.exception),
                    "received 1000 (OK); then sent 1000 (OK)",
                )

    async def test_connection_handler_raises_exception(self):
        """Connection handler raises an exception."""
        async with run_server(crash) as server:
            async with run_client(server) as client:
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
            async with run_server(sock=sock, host=None, port=None):
                uri = "ws://{}:{}/".format(*sock.getsockname())
                async with run_client(uri) as client:
                    await self.assertEval(client, "ws.protocol.state.name", "OPEN")

    async def test_select_subprotocol(self):
        """Server selects a subprotocol with the select_subprotocol callable."""

        def select_subprotocol(ws, subprotocols):
            ws.select_subprotocol_ran = True
            assert "chat" in subprotocols
            return "chat"

        async with run_server(
            subprotocols=["chat"],
            select_subprotocol=select_subprotocol,
        ) as server:
            async with run_client(server, subprotocols=["chat"]) as client:
                await self.assertEval(client, "ws.select_subprotocol_ran", "True")
                await self.assertEval(client, "ws.subprotocol", "chat")

    async def test_select_subprotocol_rejects_handshake(self):
        """Server rejects handshake if select_subprotocol raises NegotiationError."""

        def select_subprotocol(ws, subprotocols):
            raise NegotiationError

        async with run_server(select_subprotocol=select_subprotocol) as server:
            with self.assertRaises(InvalidStatus) as raised:
                async with run_client(server):
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
                async with run_client(server):
                    self.fail("did not raise")
            self.assertEqual(
                str(raised.exception),
                "server rejected WebSocket connection: HTTP 500",
            )

    async def test_process_request(self):
        """Server runs process_request before processing the handshake."""

        def process_request(ws, request):
            self.assertIsInstance(request, Request)
            ws.process_request_ran = True

        async with run_server(process_request=process_request) as server:
            async with run_client(server) as client:
                await self.assertEval(client, "ws.process_request_ran", "True")

    async def test_async_process_request(self):
        """Server runs async process_request before processing the handshake."""

        async def process_request(ws, request):
            self.assertIsInstance(request, Request)
            ws.process_request_ran = True

        async with run_server(process_request=process_request) as server:
            async with run_client(server) as client:
                await self.assertEval(client, "ws.process_request_ran", "True")

    async def test_process_request_abort_handshake(self):
        """Server aborts handshake if process_request returns a response."""

        def process_request(ws, request):
            return ws.protocol.reject(http.HTTPStatus.FORBIDDEN, "Forbidden")

        async with run_server(process_request=process_request) as server:
            with self.assertRaises(InvalidStatus) as raised:
                async with run_client(server):
                    self.fail("did not raise")
            self.assertEqual(
                str(raised.exception),
                "server rejected WebSocket connection: HTTP 403",
            )

    async def test_async_process_request_abort_handshake(self):
        """Server aborts handshake if async process_request returns a response."""

        async def process_request(ws, request):
            return ws.protocol.reject(http.HTTPStatus.FORBIDDEN, "Forbidden")

        async with run_server(process_request=process_request) as server:
            with self.assertRaises(InvalidStatus) as raised:
                async with run_client(server):
                    self.fail("did not raise")
            self.assertEqual(
                str(raised.exception),
                "server rejected WebSocket connection: HTTP 403",
            )

    async def test_process_request_raises_exception(self):
        """Server returns an error if process_request raises an exception."""

        def process_request(ws, request):
            raise RuntimeError

        async with run_server(process_request=process_request) as server:
            with self.assertRaises(InvalidStatus) as raised:
                async with run_client(server):
                    self.fail("did not raise")
            self.assertEqual(
                str(raised.exception),
                "server rejected WebSocket connection: HTTP 500",
            )

    async def test_async_process_request_raises_exception(self):
        """Server returns an error if async process_request raises an exception."""

        async def process_request(ws, request):
            raise RuntimeError

        async with run_server(process_request=process_request) as server:
            with self.assertRaises(InvalidStatus) as raised:
                async with run_client(server):
                    self.fail("did not raise")
            self.assertEqual(
                str(raised.exception),
                "server rejected WebSocket connection: HTTP 500",
            )

    async def test_process_response(self):
        """Server runs process_response after processing the handshake."""

        def process_response(ws, request, response):
            self.assertIsInstance(request, Request)
            self.assertIsInstance(response, Response)
            ws.process_response_ran = True

        async with run_server(process_response=process_response) as server:
            async with run_client(server) as client:
                await self.assertEval(client, "ws.process_response_ran", "True")

    async def test_async_process_response(self):
        """Server runs async process_response after processing the handshake."""

        async def process_response(ws, request, response):
            self.assertIsInstance(request, Request)
            self.assertIsInstance(response, Response)
            ws.process_response_ran = True

        async with run_server(process_response=process_response) as server:
            async with run_client(server) as client:
                await self.assertEval(client, "ws.process_response_ran", "True")

    async def test_process_response_override_response(self):
        """Server runs process_response and overrides the handshake response."""

        def process_response(ws, request, response):
            headers = response.headers.copy()
            headers["X-ProcessResponse-Ran"] = "true"
            return dataclasses.replace(response, headers=headers)

        async with run_server(process_response=process_response) as server:
            async with run_client(server) as client:
                self.assertEqual(
                    client.response.headers["X-ProcessResponse-Ran"], "true"
                )

    async def test_async_process_response_override_response(self):
        """Server runs async process_response and overrides the handshake response."""

        async def process_response(ws, request, response):
            headers = response.headers.copy()
            headers["X-ProcessResponse-Ran"] = "true"
            return dataclasses.replace(response, headers=headers)

        async with run_server(process_response=process_response) as server:
            async with run_client(server) as client:
                self.assertEqual(
                    client.response.headers["X-ProcessResponse-Ran"], "true"
                )

    async def test_process_response_raises_exception(self):
        """Server returns an error if process_response raises an exception."""

        def process_response(ws, request, response):
            raise RuntimeError

        async with run_server(process_response=process_response) as server:
            with self.assertRaises(InvalidStatus) as raised:
                async with run_client(server):
                    self.fail("did not raise")
            self.assertEqual(
                str(raised.exception),
                "server rejected WebSocket connection: HTTP 500",
            )

    async def test_async_process_response_raises_exception(self):
        """Server returns an error if async process_response raises an exception."""

        async def process_response(ws, request, response):
            raise RuntimeError

        async with run_server(process_response=process_response) as server:
            with self.assertRaises(InvalidStatus) as raised:
                async with run_client(server):
                    self.fail("did not raise")
            self.assertEqual(
                str(raised.exception),
                "server rejected WebSocket connection: HTTP 500",
            )

    async def test_override_server(self):
        """Server can override Server header with server_header."""
        async with run_server(server_header="Neo") as server:
            async with run_client(server) as client:
                await self.assertEval(client, "ws.response.headers['Server']", "Neo")

    async def test_remove_server(self):
        """Server can remove Server header with server_header."""
        async with run_server(server_header=None) as server:
            async with run_client(server) as client:
                await self.assertEval(
                    client, "'Server' in ws.response.headers", "False"
                )

    async def test_compression_is_enabled(self):
        """Server enables compression by default."""
        async with run_server() as server:
            async with run_client(server) as client:
                await self.assertEval(
                    client,
                    "[type(ext).__name__ for ext in ws.protocol.extensions]",
                    "['PerMessageDeflate']",
                )

    async def test_disable_compression(self):
        """Server disables compression."""
        async with run_server(compression=None) as server:
            async with run_client(server) as client:
                await self.assertEval(client, "ws.protocol.extensions", "[]")

    async def test_custom_connection_factory(self):
        """Server runs ServerConnection factory provided in create_connection."""

        def create_connection(*args, **kwargs):
            server = ServerConnection(*args, **kwargs)
            server.create_connection_ran = True
            return server

        async with run_server(create_connection=create_connection) as server:
            async with run_client(server) as client:
                await self.assertEval(client, "ws.create_connection_ran", "True")

    async def test_handshake_fails(self):
        """Server receives connection from client but the handshake fails."""

        def remove_key_header(self, request):
            del request.headers["Sec-WebSocket-Key"]

        async with run_server(process_request=remove_key_header) as server:
            with self.assertRaises(InvalidStatus) as raised:
                async with run_client(server):
                    self.fail("did not raise")
            self.assertEqual(
                str(raised.exception),
                "server rejected WebSocket connection: HTTP 400",
            )

    async def test_timeout_during_handshake(self):
        """Server times out before receiving handshake request from client."""
        async with run_server(open_timeout=MS) as server:
            reader, writer = await asyncio.open_connection(
                *get_server_host_port(server)
            )
            try:
                self.assertEqual(await reader.read(4096), b"")
            finally:
                writer.close()

    async def test_connection_closed_during_handshake(self):
        """Server reads EOF before receiving handshake request from client."""
        async with run_server() as server:
            _reader, writer = await asyncio.open_connection(
                *get_server_host_port(server)
            )
            writer.close()


SSL_OBJECT = "ws.transport.get_extra_info('ssl_object')"


class SecureServerTests(EvalShellMixin, unittest.IsolatedAsyncioTestCase):
    async def test_connection(self):
        """Server receives secure connection from client."""
        async with run_server(ssl=SERVER_CONTEXT) as server:
            async with run_client(server, ssl=CLIENT_CONTEXT) as client:
                await self.assertEval(client, "ws.protocol.state.name", "OPEN")
                await self.assertEval(client, SSL_OBJECT + ".version()[:3]", "TLS")

    async def test_timeout_during_tls_handshake(self):
        """Server times out before receiving TLS handshake request from client."""
        async with run_server(ssl=SERVER_CONTEXT, open_timeout=MS) as server:
            reader, writer = await asyncio.open_connection(
                *get_server_host_port(server)
            )
            try:
                self.assertEqual(await reader.read(4096), b"")
            finally:
                writer.close()

    async def test_connection_closed_during_tls_handshake(self):
        """Server reads EOF before receiving TLS handshake request from client."""
        async with run_server(ssl=SERVER_CONTEXT) as server:
            _reader, writer = await asyncio.open_connection(
                *get_server_host_port(server)
            )
            writer.close()


@unittest.skipUnless(hasattr(socket, "AF_UNIX"), "this test requires Unix sockets")
class UnixServerTests(EvalShellMixin, unittest.IsolatedAsyncioTestCase):
    async def test_connection(self):
        """Server receives connection from client over a Unix socket."""
        with temp_unix_socket_path() as path:
            async with run_unix_server(path):
                async with run_unix_client(path) as client:
                    await self.assertEval(client, "ws.protocol.state.name", "OPEN")


@unittest.skipUnless(hasattr(socket, "AF_UNIX"), "this test requires Unix sockets")
class SecureUnixServerTests(EvalShellMixin, unittest.IsolatedAsyncioTestCase):
    async def test_connection(self):
        """Server receives secure connection from client over a Unix socket."""
        with temp_unix_socket_path() as path:
            async with run_unix_server(path, ssl=SERVER_CONTEXT):
                async with run_unix_client(path, ssl=CLIENT_CONTEXT) as client:
                    await self.assertEval(client, "ws.protocol.state.name", "OPEN")
                    await self.assertEval(client, SSL_OBJECT + ".version()[:3]", "TLS")


class ServerUsageErrorsTests(unittest.IsolatedAsyncioTestCase):
    async def test_unix_without_path_or_sock(self):
        """Unix server requires path when sock isn't provided."""
        with self.assertRaises(ValueError) as raised:
            await unix_serve(eval_shell)
        self.assertEqual(
            str(raised.exception),
            "path was not specified, and no sock specified",
        )

    async def test_unix_with_path_and_sock(self):
        """Unix server rejects path when sock is provided."""
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.addCleanup(sock.close)
        with self.assertRaises(ValueError) as raised:
            await unix_serve(eval_shell, path="/", sock=sock)
        self.assertEqual(
            str(raised.exception),
            "path and sock can not be specified at the same time",
        )

    async def test_invalid_subprotocol(self):
        """Server rejects single value of subprotocols."""
        with self.assertRaises(TypeError) as raised:
            await serve(eval_shell, subprotocols="chat")
        self.assertEqual(
            str(raised.exception),
            "subprotocols must be a list, not a str",
        )

    async def test_unsupported_compression(self):
        """Server rejects incorrect value of compression."""
        with self.assertRaises(ValueError) as raised:
            await serve(eval_shell, compression=False)
        self.assertEqual(
            str(raised.exception),
            "unsupported compression: False",
        )


class WebSocketServerTests(unittest.IsolatedAsyncioTestCase):
    async def test_logger(self):
        """WebSocketServer accepts a logger argument."""
        logger = logging.getLogger("test")
        async with run_server(logger=logger) as server:
            self.assertIs(server.logger, logger)


#     async def test_fileno(self):
#         """WebSocketServer provides a fileno attribute."""
#         async with run_server() as server:
#             self.assertIsInstance(server.fileno(), int)

#     async def test_shutdown(self):
#         """WebSocketServer provides a shutdown method."""
#         async with run_server() as server:
#             server.shutdown()
#             # Check that the server socket is closed.
#             with self.assertRaises(OSError):
#                 server.socket.accept()
