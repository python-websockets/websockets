import asyncio
import socket
import ssl
import unittest

from websockets.asyncio.client import *
from websockets.exceptions import InvalidHandshake, InvalidURI
from websockets.extensions.permessage_deflate import PerMessageDeflate

from ..utils import CLIENT_CONTEXT, MS, SERVER_CONTEXT, temp_unix_socket_path
from .client import run_client, run_unix_client
from .server import do_nothing, get_server_host_port, run_server, run_unix_server


class ClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_connection(self):
        """Client connects to server and the handshake succeeds."""
        async with run_server() as server:
            async with run_client(server) as client:
                self.assertEqual(client.protocol.state.name, "OPEN")

    async def test_existing_socket(self):
        """Client connects using a pre-existing socket."""
        async with run_server() as server:
            with socket.create_connection(get_server_host_port(server)) as sock:
                # Use a non-existing domain to ensure we connect to the right socket.
                async with run_client("ws://invalid/", sock=sock) as client:
                    self.assertEqual(client.protocol.state.name, "OPEN")

    async def test_additional_headers(self):
        """Client can set additional headers with additional_headers."""
        async with run_server() as server:
            async with run_client(
                server, additional_headers={"Authorization": "Bearer ..."}
            ) as client:
                self.assertEqual(client.request.headers["Authorization"], "Bearer ...")

    async def test_override_user_agent(self):
        """Client can override User-Agent header with user_agent_header."""
        async with run_server() as server:
            async with run_client(server, user_agent_header="Smith") as client:
                self.assertEqual(client.request.headers["User-Agent"], "Smith")

    async def test_remove_user_agent(self):
        """Client can remove User-Agent header with user_agent_header."""
        async with run_server() as server:
            async with run_client(server, user_agent_header=None) as client:
                self.assertNotIn("User-Agent", client.request.headers)

    async def test_compression_is_enabled(self):
        """Client enables compression by default."""
        async with run_server() as server:
            async with run_client(server) as client:
                self.assertEqual(
                    [type(ext) for ext in client.protocol.extensions],
                    [PerMessageDeflate],
                )

    async def test_disable_compression(self):
        """Client disables compression."""
        async with run_server() as server:
            async with run_client(server, compression=None) as client:
                self.assertEqual(client.protocol.extensions, [])

    async def test_custom_connection_factory(self):
        """Client runs ClientConnection factory provided in create_connection."""

        def create_connection(*args, **kwargs):
            client = ClientConnection(*args, **kwargs)
            client.create_connection_ran = True
            return client

        async with run_server() as server:
            async with run_client(
                server, create_connection=create_connection
            ) as client:
                self.assertTrue(client.create_connection_ran)

    async def test_invalid_uri(self):
        """Client receives an invalid URI."""
        with self.assertRaises(InvalidURI):
            async with run_client("http://localhost"):  # invalid scheme
                self.fail("did not raise")

    async def test_tcp_connection_fails(self):
        """Client fails to connect to server."""
        with self.assertRaises(OSError):
            async with run_client("ws://localhost:54321"):  # invalid port
                self.fail("did not raise")

    async def test_handshake_fails(self):
        """Client connects to server but the handshake fails."""

        def remove_accept_header(self, request, response):
            del response.headers["Sec-WebSocket-Accept"]

        # The connection will be open for the server but failed for the client.
        # Use a connection handler that exits immediately to avoid an exception.
        async with run_server(
            do_nothing, process_response=remove_accept_header
        ) as server:
            with self.assertRaises(InvalidHandshake) as raised:
                async with run_client(server, close_timeout=MS):
                    self.fail("did not raise")
            self.assertEqual(
                str(raised.exception),
                "missing Sec-WebSocket-Accept header",
            )

    async def test_timeout_during_handshake(self):
        """Client times out before receiving handshake response from server."""
        gate = asyncio.get_running_loop().create_future()

        async def stall_connection(self, request):
            await gate

        # The connection will be open for the server but failed for the client.
        # Use a connection handler that exits immediately to avoid an exception.
        async with run_server(do_nothing, process_request=stall_connection) as server:
            try:
                with self.assertRaises(TimeoutError) as raised:
                    async with run_client(server, open_timeout=2 * MS):
                        self.fail("did not raise")
                self.assertEqual(
                    str(raised.exception),
                    "timed out during handshake",
                )
            finally:
                gate.set_result(None)

    async def test_connection_closed_during_handshake(self):
        """Client reads EOF before receiving handshake response from server."""

        def close_connection(self, request):
            self.close_transport()

        async with run_server(process_request=close_connection) as server:
            with self.assertRaises(ConnectionError) as raised:
                async with run_client(server):
                    self.fail("did not raise")
            self.assertEqual(
                str(raised.exception),
                "connection closed during handshake",
            )


class SecureClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_connection(self):
        """Client connects to server securely."""
        async with run_server(ssl=SERVER_CONTEXT) as server:
            async with run_client(server, ssl=CLIENT_CONTEXT) as client:
                self.assertEqual(client.protocol.state.name, "OPEN")
                ssl_object = client.transport.get_extra_info("ssl_object")
                self.assertEqual(ssl_object.version()[:3], "TLS")

    async def test_set_server_hostname_implicitly(self):
        """Client sets server_hostname to the host in the WebSocket URI."""
        with temp_unix_socket_path() as path:
            async with run_unix_server(path, ssl=SERVER_CONTEXT):
                async with run_unix_client(
                    path,
                    ssl=CLIENT_CONTEXT,
                    uri="wss://overridden/",
                ) as client:
                    ssl_object = client.transport.get_extra_info("ssl_object")
                    self.assertEqual(ssl_object.server_hostname, "overridden")

    async def test_set_server_hostname_explicitly(self):
        """Client sets server_hostname to the value provided in argument."""
        with temp_unix_socket_path() as path:
            async with run_unix_server(path, ssl=SERVER_CONTEXT):
                async with run_unix_client(
                    path,
                    ssl=CLIENT_CONTEXT,
                    server_hostname="overridden",
                ) as client:
                    ssl_object = client.transport.get_extra_info("ssl_object")
                    self.assertEqual(ssl_object.server_hostname, "overridden")

    async def test_reject_invalid_server_certificate(self):
        """Client rejects certificate where server certificate isn't trusted."""
        async with run_server(ssl=SERVER_CONTEXT) as server:
            with self.assertRaises(ssl.SSLCertVerificationError) as raised:
                # The test certificate isn't trusted system-wide.
                async with run_client(server, secure=True):
                    self.fail("did not raise")
            self.assertIn(
                "certificate verify failed: self signed certificate",
                str(raised.exception).replace("-", " "),
            )

    async def test_reject_invalid_server_hostname(self):
        """Client rejects certificate where server hostname doesn't match."""
        async with run_server(ssl=SERVER_CONTEXT) as server:
            with self.assertRaises(ssl.SSLCertVerificationError) as raised:
                # This hostname isn't included in the test certificate.
                async with run_client(
                    server, ssl=CLIENT_CONTEXT, server_hostname="invalid"
                ):
                    self.fail("did not raise")
            self.assertIn(
                "certificate verify failed: Hostname mismatch",
                str(raised.exception),
            )


@unittest.skipUnless(hasattr(socket, "AF_UNIX"), "this test requires Unix sockets")
class UnixClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_connection(self):
        """Client connects to server over a Unix socket."""
        with temp_unix_socket_path() as path:
            async with run_unix_server(path):
                async with run_unix_client(path) as client:
                    self.assertEqual(client.protocol.state.name, "OPEN")

    async def test_set_host_header(self):
        """Client sets the Host header to the host in the WebSocket URI."""
        # This is part of the documented behavior of unix_connect().
        with temp_unix_socket_path() as path:
            async with run_unix_server(path):
                async with run_unix_client(path, uri="ws://overridden/") as client:
                    self.assertEqual(client.request.headers["Host"], "overridden")


@unittest.skipUnless(hasattr(socket, "AF_UNIX"), "this test requires Unix sockets")
class SecureUnixClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_connection(self):
        """Client connects to server securely over a Unix socket."""
        with temp_unix_socket_path() as path:
            async with run_unix_server(path, ssl=SERVER_CONTEXT):
                async with run_unix_client(path, ssl=CLIENT_CONTEXT) as client:
                    self.assertEqual(client.protocol.state.name, "OPEN")
                    ssl_object = client.transport.get_extra_info("ssl_object")
                    self.assertEqual(ssl_object.version()[:3], "TLS")

    async def test_set_server_hostname(self):
        """Client sets server_hostname to the host in the WebSocket URI."""
        # This is part of the documented behavior of unix_connect().
        with temp_unix_socket_path() as path:
            async with run_unix_server(path, ssl=SERVER_CONTEXT):
                async with run_unix_client(
                    path,
                    ssl=CLIENT_CONTEXT,
                    uri="wss://overridden/",
                ) as client:
                    ssl_object = client.transport.get_extra_info("ssl_object")
                    self.assertEqual(ssl_object.server_hostname, "overridden")


class ClientUsageErrorsTests(unittest.IsolatedAsyncioTestCase):
    async def test_ssl_without_secure_uri(self):
        """Client rejects ssl when URI isn't secure."""
        with self.assertRaises(TypeError) as raised:
            await connect("ws://localhost/", ssl=CLIENT_CONTEXT)
        self.assertEqual(
            str(raised.exception),
            "ssl argument is incompatible with a ws:// URI",
        )

    async def test_secure_uri_without_ssl(self):
        """Client rejects ssl when URI isn't secure."""
        with self.assertRaises(TypeError) as raised:
            await connect("ws://localhost/", ssl=CLIENT_CONTEXT)
        self.assertEqual(
            str(raised.exception),
            "ssl argument is incompatible with a ws:// URI",
        )

    async def test_unix_without_path_or_sock(self):
        """Unix client requires path when sock isn't provided."""
        with self.assertRaises(ValueError) as raised:
            await unix_connect()
        self.assertEqual(
            str(raised.exception),
            "no path and sock were specified",
        )

    async def test_unix_with_path_and_sock(self):
        """Unix client rejects path when sock is provided."""
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.addCleanup(sock.close)
        with self.assertRaises(ValueError) as raised:
            await unix_connect(path="/", sock=sock)
        self.assertEqual(
            str(raised.exception),
            "path and sock can not be specified at the same time",
        )

    async def test_invalid_subprotocol(self):
        """Client rejects single value of subprotocols."""
        with self.assertRaises(TypeError) as raised:
            await connect("ws://localhost/", subprotocols="chat")
        self.assertEqual(
            str(raised.exception),
            "subprotocols must be a list, not a str",
        )

    async def test_unsupported_compression(self):
        """Client rejects incorrect value of compression."""
        with self.assertRaises(ValueError) as raised:
            await connect("ws://localhost/", compression=False)
        self.assertEqual(
            str(raised.exception),
            "unsupported compression: False",
        )
