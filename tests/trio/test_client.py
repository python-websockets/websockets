import contextlib
import http
import logging
import os
import socket
import ssl
import sys
import unittest
from unittest.mock import patch

import trio

from websockets.client import backoff
from websockets.exceptions import (
    InvalidHandshake,
    InvalidMessage,
    InvalidProxy,
    InvalidProxyMessage,
    InvalidStatus,
    InvalidURI,
    ProxyError,
    SecurityError,
)
from websockets.extensions.permessage_deflate import PerMessageDeflate
from websockets.trio.client import *

from ..proxy import ProxyMixin
from ..utils import CLIENT_CONTEXT, MS, SERVER_CONTEXT
from .server import get_host_port, get_uri, run_server
from .utils import IsolatedTrioTestCase


@contextlib.asynccontextmanager
async def short_backoff_delay():
    defaults = backoff.__defaults__
    backoff.__defaults__ = (
        defaults[0] * MS,
        defaults[1] * MS,
        defaults[2] * MS,
        defaults[3],
    )
    try:
        yield
    finally:
        backoff.__defaults__ = defaults


@contextlib.asynccontextmanager
async def few_redirects():
    from websockets.trio import client

    max_redirects = client.MAX_REDIRECTS
    client.MAX_REDIRECTS = 2
    try:
        yield
    finally:
        client.MAX_REDIRECTS = max_redirects


class ClientTests(IsolatedTrioTestCase):
    async def test_connection(self):
        """Client connects to server."""
        async with run_server() as server:
            async with connect(get_uri(server)) as client:
                self.assertEqual(client.protocol.state.name, "OPEN")

    async def test_explicit_host_port(self):
        """Client connects using an explicit host / port."""
        async with run_server() as server:
            host, port = get_host_port(server.listeners)
            async with connect("ws://overridden/", host=host, port=port) as client:
                self.assertEqual(client.protocol.state.name, "OPEN")

    async def test_existing_stream(self):
        """Client connects using a pre-existing stream."""
        async with run_server() as server:
            stream = await trio.open_tcp_stream(*get_host_port(server.listeners))
            # Use a non-existing domain to ensure we connect via stream.
            async with connect("ws://invalid/", stream=stream) as client:
                self.assertEqual(client.protocol.state.name, "OPEN")

    async def test_compression_is_enabled(self):
        """Client enables compression by default."""
        async with run_server() as server:
            async with connect(get_uri(server)) as client:
                self.assertEqual(
                    [type(ext) for ext in client.protocol.extensions],
                    [PerMessageDeflate],
                )

    async def test_disable_compression(self):
        """Client disables compression."""
        async with run_server() as server:
            async with connect(get_uri(server), compression=None) as client:
                self.assertEqual(client.protocol.extensions, [])

    async def test_additional_headers(self):
        """Client can set additional headers with additional_headers."""
        async with run_server() as server:
            async with connect(
                get_uri(server), additional_headers={"Authorization": "Bearer ..."}
            ) as client:
                self.assertEqual(client.request.headers["Authorization"], "Bearer ...")

    async def test_override_user_agent(self):
        """Client can override User-Agent header with user_agent_header."""
        async with run_server() as server:
            async with connect(get_uri(server), user_agent_header="Smith") as client:
                self.assertEqual(client.request.headers["User-Agent"], "Smith")

    async def test_remove_user_agent(self):
        """Client can remove User-Agent header with user_agent_header."""
        async with run_server() as server:
            async with connect(get_uri(server), user_agent_header=None) as client:
                self.assertNotIn("User-Agent", client.request.headers)

    async def test_legacy_user_agent(self):
        """Client can override User-Agent header with additional_headers."""
        async with run_server() as server:
            async with connect(
                get_uri(server), additional_headers={"User-Agent": "Smith"}
            ) as client:
                self.assertEqual(client.request.headers["User-Agent"], "Smith")

    async def test_keepalive_is_enabled(self):
        """Client enables keepalive and measures latency by default."""
        async with run_server() as server:
            async with connect(get_uri(server), ping_interval=MS) as client:
                self.assertEqual(client.latency, 0)
                await trio.sleep(2 * MS)
                self.assertGreater(client.latency, 0)

    async def test_disable_keepalive(self):
        """Client disables keepalive."""
        async with run_server() as server:
            async with connect(get_uri(server), ping_interval=None) as client:
                await trio.sleep(2 * MS)
                self.assertEqual(client.latency, 0)

    async def test_logger(self):
        """Client accepts a logger argument."""
        logger = logging.getLogger("test")
        async with run_server() as server:
            async with connect(get_uri(server), logger=logger) as client:
                self.assertEqual(client.logger.name, logger.name)

    async def test_custom_connection_factory(self):
        """Client runs ClientConnection factory provided in create_connection."""

        def create_connection(*args, **kwargs):
            client = ClientConnection(*args, **kwargs)
            client.create_connection_ran = True
            return client

        async with run_server() as server:
            async with connect(
                get_uri(server), create_connection=create_connection
            ) as client:
                self.assertTrue(client.create_connection_ran)

    @short_backoff_delay()
    async def test_reconnect(self):
        """Client reconnects to server."""
        iterations = 0
        successful = 0

        async def process_request(connection, request):
            nonlocal iterations
            iterations += 1
            # Retriable errors
            if iterations == 1:
                await trio.sleep(3 * MS)
            elif iterations == 2:
                await connection.stream.aclose()
            elif iterations == 3:
                return connection.respond(http.HTTPStatus.SERVICE_UNAVAILABLE, "🚒")
            # Fatal error
            elif iterations == 6:
                return connection.respond(http.HTTPStatus.PAYMENT_REQUIRED, "💸")

        async with run_server(process_request=process_request) as server:
            with self.assertRaises(InvalidStatus) as raised:
                async for client in connect(get_uri(server), open_timeout=3 * MS):
                    self.assertEqual(client.protocol.state.name, "OPEN")
                    successful += 1

        self.assertEqual(
            str(raised.exception),
            "server rejected WebSocket connection: HTTP 402",
        )
        self.assertEqual(iterations, 6)
        self.assertEqual(successful, 2)

    @short_backoff_delay()
    async def test_reconnect_with_custom_process_exception(self):
        """Client runs process_exception to tell if errors are retryable or fatal."""
        iteration = 0

        def process_request(connection, request):
            nonlocal iteration
            iteration += 1
            if iteration == 1:
                return connection.respond(http.HTTPStatus.SERVICE_UNAVAILABLE, "🚒")
            return connection.respond(http.HTTPStatus.IM_A_TEAPOT, "🫖")

        def process_exception(exc):
            if isinstance(exc, InvalidStatus):
                if 500 <= exc.response.status_code < 600:
                    return None
                if exc.response.status_code == 418:
                    return Exception("🫖 💔 ☕️")
            self.fail("unexpected exception")

        async with run_server(process_request=process_request) as server:
            with self.assertRaises(Exception) as raised:
                async for _ in connect(
                    get_uri(server), process_exception=process_exception
                ):
                    self.fail("did not raise")

        self.assertEqual(iteration, 2)
        self.assertEqual(
            str(raised.exception),
            "🫖 💔 ☕️",
        )

    @short_backoff_delay()
    async def test_reconnect_with_custom_process_exception_raising_exception(self):
        """Client supports raising an exception in process_exception."""

        def process_request(connection, request):
            return connection.respond(http.HTTPStatus.IM_A_TEAPOT, "🫖")

        def process_exception(exc):
            if isinstance(exc, InvalidStatus) and exc.response.status_code == 418:
                raise Exception("🫖 💔 ☕️")
            self.fail("unexpected exception")

        async with run_server(process_request=process_request) as server:
            with self.assertRaises(Exception) as raised:
                async for _ in connect(
                    get_uri(server), process_exception=process_exception
                ):
                    self.fail("did not raise")

        self.assertEqual(
            str(raised.exception),
            "🫖 💔 ☕️",
        )

    async def test_redirect(self):
        """Client follows redirect."""

        def redirect(connection, request):
            if request.path == "/redirect":
                response = connection.respond(http.HTTPStatus.FOUND, "")
                response.headers["Location"] = "/"
                return response

        async with run_server(process_request=redirect) as server:
            async with connect(get_uri(server) + "/redirect") as client:
                self.assertEqual(client.protocol.uri.path, "/")

    async def test_cross_origin_redirect(self):
        """Client follows redirect to a secure URI on a different origin."""

        def redirect(connection, request):
            response = connection.respond(http.HTTPStatus.FOUND, "")
            response.headers["Location"] = get_uri(other_server)
            return response

        async with run_server(process_request=redirect) as server:
            async with run_server() as other_server:
                async with connect(get_uri(server)):
                    self.assertFalse(server.connections)
                    self.assertTrue(other_server.connections)

    @few_redirects()
    async def test_redirect_limit(self):
        """Client stops following redirects after limit is reached."""

        def redirect(connection, request):
            response = connection.respond(http.HTTPStatus.FOUND, "")
            response.headers["Location"] = request.path
            return response

        async with run_server(process_request=redirect) as server:
            with self.assertRaises(SecurityError) as raised:
                async with connect(get_uri(server)):
                    self.fail("did not raise")

        self.assertEqual(
            str(raised.exception),
            "more than 2 redirects",
        )

    async def test_redirect_with_explicit_host_port(self):
        """Client follows redirect with an explicit host / port."""

        def redirect(connection, request):
            if request.path == "/redirect":
                response = connection.respond(http.HTTPStatus.FOUND, "")
                response.headers["Location"] = "/"
                return response

        async with run_server(process_request=redirect) as server:
            host, port = get_host_port(server.listeners)
            async with connect(
                "ws://overridden/redirect", host=host, port=port
            ) as client:
                self.assertEqual(client.protocol.uri.path, "/")

    async def test_cross_origin_redirect_with_explicit_host_port(self):
        """Client doesn't follow cross-origin redirect with an explicit host / port."""

        def redirect(connection, request):
            response = connection.respond(http.HTTPStatus.FOUND, "")
            response.headers["Location"] = "ws://other/"
            return response

        async with run_server(process_request=redirect) as server:
            host, port = get_host_port(server.listeners)
            with self.assertRaises(ValueError) as raised:
                async with connect("ws://overridden/", host=host, port=port):
                    self.fail("did not raise")

        self.assertEqual(
            str(raised.exception),
            "cannot follow cross-origin redirect to ws://other/ "
            "with an explicit host or port",
        )

    async def test_redirect_with_existing_stream(self):
        """Client doesn't follow redirect when using a pre-existing stream."""

        def redirect(connection, request):
            response = connection.respond(http.HTTPStatus.FOUND, "")
            response.headers["Location"] = "/"
            return response

        async with run_server(process_request=redirect) as server:
            stream = await trio.open_tcp_stream(*get_host_port(server.listeners))
            with self.assertRaises(ValueError) as raised:
                # Use a non-existing domain to ensure we connect via sock.
                async with connect("ws://invalid/redirect", stream=stream):
                    self.fail("did not raise")

        self.assertEqual(
            str(raised.exception),
            "cannot follow redirect to ws://invalid/ with a preexisting stream",
        )

    async def test_invalid_uri(self):
        """Client receives an invalid URI."""
        with self.assertRaises(InvalidURI):
            async with connect("http://localhost"):  # invalid scheme
                self.fail("did not raise")

    async def test_tcp_connection_fails(self):
        """Client fails to connect to server."""
        with self.assertRaises(OSError):
            async with connect("ws://localhost:54321"):  # invalid port
                self.fail("did not raise")

    async def test_handshake_fails(self):
        """Client connects to server but the handshake fails."""

        def remove_accept_header(self, request, response):
            del response.headers["Sec-WebSocket-Accept"]

        # The connection will be open for the server but failed for the client.
        # Use a connection handler that exits immediately to avoid an exception.
        async with run_server(process_response=remove_accept_header) as server:
            with self.assertRaises(InvalidHandshake) as raised:
                async with connect(get_uri(server) + "/no-op", close_timeout=MS):
                    self.fail("did not raise")
            self.assertEqual(
                str(raised.exception),
                "missing Sec-WebSocket-Accept header",
            )

    async def test_timeout_during_handshake(self):
        """Client times out before receiving handshake response from server."""
        # Replace the WebSocket server with a TCP server that doesn't respond.
        with socket.create_server(("localhost", 0)) as sock:
            host, port = sock.getsockname()
            with self.assertRaises(TimeoutError) as raised:
                async with connect(f"ws://{host}:{port}", open_timeout=2 * MS):
                    self.fail("did not raise")
            self.assertEqual(
                str(raised.exception),
                "timed out during opening handshake",
            )

    async def test_connection_closed_during_handshake(self):
        """Client reads EOF before receiving handshake response from server."""

        async def close_connection(self, request):
            await self.stream.aclose()

        async with run_server(process_request=close_connection) as server:
            with self.assertRaises(InvalidMessage) as raised:
                async with connect(get_uri(server)):
                    self.fail("did not raise")
            self.assertEqual(
                str(raised.exception),
                "did not receive a valid HTTP response",
            )
            self.assertIsInstance(raised.exception.__cause__, EOFError)
            self.assertEqual(
                str(raised.exception.__cause__),
                "connection closed while reading HTTP status line",
            )

    async def test_http_response(self):
        """Client reads HTTP response."""

        def http_response(connection, request):
            return connection.respond(http.HTTPStatus.OK, "👌")

        async with run_server(process_request=http_response) as server:
            with self.assertRaises(InvalidStatus) as raised:
                async with connect(get_uri(server)):
                    self.fail("did not raise")

        self.assertEqual(raised.exception.response.status_code, 200)
        self.assertEqual(raised.exception.response.body.decode(), "👌")

    async def test_http_response_without_content_length(self):
        """Client reads HTTP response without a Content-Length header."""

        def http_response(connection, request):
            response = connection.respond(http.HTTPStatus.OK, "👌")
            del response.headers["Content-Length"]
            return response

        async with run_server(process_request=http_response) as server:
            with self.assertRaises(InvalidStatus) as raised:
                async with connect(get_uri(server)):
                    self.fail("did not raise")

        self.assertEqual(raised.exception.response.status_code, 200)
        self.assertEqual(raised.exception.response.body.decode(), "👌")

    async def test_junk_handshake(self):
        """Client closes the connection when receiving non-HTTP response from server."""

        async def junk(stream):
            # Wait for the client to send the handshake request.
            await trio.testing.wait_all_tasks_blocked()
            await stream.send_all(b"220 smtp.invalid ESMTP Postfix\r\n")
            # Wait for the client to close the connection.
            await stream.receive_some()
            await stream.aclose()

        async with trio.open_nursery() as nursery:
            try:
                listeners = await nursery.start(trio.serve_tcp, junk, 0)
                host, port = get_host_port(listeners)
                with self.assertRaises(InvalidMessage) as raised:
                    async with connect(f"ws://{host}:{port}"):
                        self.fail("did not raise")
                self.assertEqual(
                    str(raised.exception),
                    "did not receive a valid HTTP response",
                )
                self.assertIsInstance(raised.exception.__cause__, ValueError)
                self.assertEqual(
                    str(raised.exception.__cause__),
                    "unsupported protocol; expected HTTP/1.1: "
                    "220 smtp.invalid ESMTP Postfix",
                )
            finally:
                nursery.cancel_scope.cancel()


class SecureClientTests(IsolatedTrioTestCase):
    async def test_connection(self):
        """Client connects to server securely."""
        async with run_server(ssl=SERVER_CONTEXT) as server:
            async with connect(
                get_uri(server, secure=True), ssl=CLIENT_CONTEXT
            ) as client:
                self.assertEqual(client.protocol.state.name, "OPEN")
                ssl_object = client.stream._ssl_object
                self.assertEqual(ssl_object.version()[:3], "TLS")

    async def test_set_server_hostname_implicitly(self):
        """Client sets server_hostname to the host in the WebSocket URI."""
        async with run_server(ssl=SERVER_CONTEXT) as server:
            host, port = get_host_port(server.listeners)
            async with connect(
                "wss://overridden/", host=host, port=port, ssl=CLIENT_CONTEXT
            ) as client:
                ssl_object = client.stream._ssl_object
                self.assertEqual(ssl_object.server_hostname, "overridden")

    async def test_set_server_hostname_explicitly(self):
        """Client sets server_hostname to the value provided in argument."""
        async with run_server(ssl=SERVER_CONTEXT) as server:
            async with connect(
                get_uri(server, secure=True),
                ssl=CLIENT_CONTEXT,
                server_hostname="overridden",
            ) as client:
                ssl_object = client.stream._ssl_object
                self.assertEqual(ssl_object.server_hostname, "overridden")

    async def test_reject_invalid_server_certificate(self):
        """Client rejects certificate where server certificate isn't trusted."""
        async with run_server(ssl=SERVER_CONTEXT) as server:
            with self.assertRaises(trio.BrokenResourceError) as raised:
                # The test certificate is self-signed.
                async with connect(get_uri(server, secure=True)):
                    self.fail("did not raise")
            self.assertIsInstance(
                raised.exception.__cause__,
                ssl.SSLCertVerificationError,
            )
            self.assertIn(
                "certificate verify failed: self signed certificate",
                str(raised.exception.__cause__).replace("-", " "),
            )

    async def test_reject_invalid_server_hostname(self):
        """Client rejects certificate where server hostname doesn't match."""
        async with run_server(ssl=SERVER_CONTEXT) as server:
            with self.assertRaises(trio.BrokenResourceError) as raised:
                # This hostname isn't included in the test certificate.
                async with connect(
                    get_uri(server, secure=True),
                    ssl=CLIENT_CONTEXT,
                    server_hostname="invalid",
                ):
                    self.fail("did not raise")
            self.assertIsInstance(
                raised.exception.__cause__,
                ssl.SSLCertVerificationError,
            )
            self.assertIn(
                "certificate verify failed: Hostname mismatch",
                str(raised.exception.__cause__),
            )

    async def test_cross_origin_redirect(self):
        """Client follows redirect to a secure URI on a different origin."""

        def redirect(connection, request):
            response = connection.respond(http.HTTPStatus.FOUND, "")
            response.headers["Location"] = get_uri(other_server, secure=True)
            return response

        async with run_server(ssl=SERVER_CONTEXT, process_request=redirect) as server:
            async with run_server(ssl=SERVER_CONTEXT) as other_server:
                async with connect(get_uri(server, secure=True), ssl=CLIENT_CONTEXT):
                    self.assertFalse(server.connections)
                    self.assertTrue(other_server.connections)

    async def test_redirect_to_insecure_uri(self):
        """Client doesn't follow redirect from secure URI to non-secure URI."""

        def redirect(connection, request):
            response = connection.respond(http.HTTPStatus.FOUND, "")
            response.headers["Location"] = insecure_uri
            return response

        async with run_server(ssl=SERVER_CONTEXT, process_request=redirect) as server:
            with self.assertRaises(SecurityError) as raised:
                secure_uri = get_uri(server, secure=True)
                insecure_uri = secure_uri.replace("wss://", "ws://")
                async with connect(secure_uri, ssl=CLIENT_CONTEXT):
                    self.fail("did not raise")

        self.assertEqual(
            str(raised.exception),
            f"cannot follow redirect to non-secure URI {insecure_uri}",
        )


@unittest.skipUnless("mitmproxy" in sys.modules, "mitmproxy not installed")
class SocksProxyClientTests(ProxyMixin, IsolatedTrioTestCase):
    proxy_mode = "socks5@51080"

    @patch.dict(os.environ, {"socks_proxy": "http://localhost:51080"})
    async def test_socks_proxy(self):
        """Client connects to server through a SOCKS5 proxy."""
        async with run_server() as server:
            async with connect(get_uri(server)) as client:
                self.assertEqual(client.protocol.state.name, "OPEN")
        self.assertNumFlows(1)

    @patch.dict(os.environ, {"socks_proxy": "http://localhost:51080"})
    async def test_secure_socks_proxy(self):
        """Client connects to server securely through a SOCKS5 proxy."""
        async with run_server(ssl=SERVER_CONTEXT) as server:
            async with connect(
                get_uri(server, secure=True), ssl=CLIENT_CONTEXT
            ) as client:
                self.assertEqual(client.protocol.state.name, "OPEN")
        self.assertNumFlows(1)

    @patch.dict(os.environ, {"socks_proxy": "http://hello:iloveyou@localhost:51080"})
    async def test_authenticated_socks_proxy(self):
        """Client connects to server through an authenticated SOCKS5 proxy."""
        try:
            self.proxy_options.update(proxyauth="hello:iloveyou")
            async with run_server() as server:
                async with connect(get_uri(server)) as client:
                    self.assertEqual(client.protocol.state.name, "OPEN")
        finally:
            self.proxy_options.update(proxyauth=None)
        self.assertNumFlows(1)

    @patch.dict(os.environ, {"socks_proxy": "http://localhost:51080"})
    async def test_authenticated_socks_proxy_error(self):
        """Client fails to authenticate to the SOCKS5 proxy."""
        from python_socks import ProxyError as SocksProxyError

        try:
            self.proxy_options.update(proxyauth="any")
            with self.assertRaises(ProxyError) as raised:
                async with connect("ws://example.com/"):
                    self.fail("did not raise")
        finally:
            self.proxy_options.update(proxyauth=None)
        self.assertEqual(
            str(raised.exception),
            "failed to connect to SOCKS proxy",
        )
        self.assertIsInstance(raised.exception.__cause__, SocksProxyError)
        self.assertNumFlows(0)

    @patch.dict(os.environ, {"socks_proxy": "http://localhost:61080"})  # bad port
    async def test_socks_proxy_connection_failure(self):
        """Client fails to connect to the SOCKS5 proxy."""
        from python_socks import ProxyConnectionError as SocksProxyConnectionError

        with self.assertRaises(OSError) as raised:
            async with connect("ws://example.com/"):
                self.fail("did not raise")
        # Don't test str(raised.exception) because we don't control it.
        self.assertIsInstance(raised.exception, SocksProxyConnectionError)
        self.assertNumFlows(0)

    async def test_socks_proxy_connection_timeout(self):
        """Client times out while connecting to the SOCKS5 proxy."""
        # Replace the proxy with a TCP server that doesn't respond.
        with socket.create_server(("localhost", 0)) as sock:
            host, port = sock.getsockname()
            with patch.dict(os.environ, {"socks_proxy": f"http://{host}:{port}"}):
                with self.assertRaises(TimeoutError) as raised:
                    async with connect("ws://example.com/", open_timeout=2 * MS):
                        self.fail("did not raise")
        self.assertEqual(
            str(raised.exception),
            "timed out during opening handshake",
        )
        self.assertNumFlows(0)

    async def test_explicit_socks_proxy(self):
        """Client connects to server through a SOCKS5 proxy set explicitly."""
        async with run_server() as server:
            async with connect(
                get_uri(server),
                # Take this opportunity to test socks5 instead of socks5h.
                proxy="socks5://localhost:51080",
            ) as client:
                self.assertEqual(client.protocol.state.name, "OPEN")
        self.assertNumFlows(1)

    @patch.dict(os.environ, {"socks_proxy": "http://localhost:51080"})
    async def test_ignore_proxy_with_existing_stream(self):
        """Cli ent connects using a pre-existing stream."""
        async with run_server() as server:
            stream = await trio.open_tcp_stream(*get_host_port(server.listeners))
            # Use a non-existing domain to ensure we connect via stream.
            async with connect("ws://invalid/", stream=stream) as client:
                self.assertEqual(client.protocol.state.name, "OPEN")
        self.assertNumFlows(0)


@unittest.skipUnless("mitmproxy" in sys.modules, "mitmproxy not installed")
class HTTPProxyClientTests(ProxyMixin, IsolatedTrioTestCase):
    proxy_mode = "regular@58080"

    @patch.dict(os.environ, {"https_proxy": "http://localhost:58080"})
    async def test_http_proxy(self):
        """Client connects to server through an HTTP proxy."""
        async with run_server() as server:
            async with connect(get_uri(server)) as client:
                self.assertEqual(client.protocol.state.name, "OPEN")
        self.assertNumFlows(1)

    @patch.dict(os.environ, {"https_proxy": "http://localhost:58080"})
    async def test_secure_http_proxy(self):
        """Client connects to server securely through an HTTP proxy."""
        async with run_server(ssl=SERVER_CONTEXT) as server:
            async with connect(
                get_uri(server, secure=True), ssl=CLIENT_CONTEXT
            ) as client:
                self.assertEqual(client.protocol.state.name, "OPEN")
                ssl_object = client.stream._ssl_object
                self.assertEqual(ssl_object.version()[:3], "TLS")
        self.assertNumFlows(1)

    @patch.dict(os.environ, {"https_proxy": "http://hello:iloveyou@localhost:58080"})
    async def test_authenticated_http_proxy(self):
        """Client connects to server through an authenticated HTTP proxy."""
        try:
            self.proxy_options.update(proxyauth="hello:iloveyou")
            async with run_server() as server:
                async with connect(get_uri(server)) as client:
                    self.assertEqual(client.protocol.state.name, "OPEN")
        finally:
            self.proxy_options.update(proxyauth=None)
        self.assertNumFlows(1)

    @patch.dict(os.environ, {"https_proxy": "http://localhost:58080"})
    async def test_authenticated_http_proxy_error(self):
        """Client fails to authenticate to the HTTP proxy."""
        try:
            self.proxy_options.update(proxyauth="any")
            with self.assertRaises(ProxyError) as raised:
                async with connect("ws://example.com/"):
                    self.fail("did not raise")
        finally:
            self.proxy_options.update(proxyauth=None)
        self.assertEqual(
            str(raised.exception),
            "proxy rejected connection: HTTP 407",
        )
        self.assertNumFlows(0)

    @patch.dict(os.environ, {"https_proxy": "http://localhost:58080"})
    async def test_http_proxy_protocol_error(self):
        """Client receives invalid data when connecting to the HTTP proxy."""
        try:
            self.proxy_options.update(break_http_connect=True)
            with self.assertRaises(InvalidProxyMessage) as raised:
                async with connect("ws://example.com/"):
                    self.fail("did not raise")
        finally:
            self.proxy_options.update(break_http_connect=False)
        self.assertEqual(
            str(raised.exception),
            "did not receive a valid HTTP response from proxy",
        )
        self.assertNumFlows(0)

    @patch.dict(os.environ, {"https_proxy": "http://localhost:58080"})
    async def test_http_proxy_connection_error(self):
        """Client receives no response when connecting to the HTTP proxy."""
        try:
            self.proxy_options.update(close_http_connect=True)
            with self.assertRaises(InvalidProxyMessage) as raised:
                async with connect("ws://example.com/"):
                    self.fail("did not raise")
        finally:
            self.proxy_options.update(close_http_connect=False)
        self.assertEqual(
            str(raised.exception),
            "did not receive a valid HTTP response from proxy",
        )
        self.assertNumFlows(0)

    @patch.dict(os.environ, {"https_proxy": "http://localhost:48080"})  # bad port
    async def test_http_proxy_connection_failure(self):
        """Client fails to connect to the HTTP proxy."""
        with self.assertRaises(OSError):
            async with connect("ws://example.com/"):
                self.fail("did not raise")
        # Don't test str(raised.exception) because we don't control it.
        self.assertNumFlows(0)

    async def test_http_proxy_connection_timeout(self):
        """Client times out while connecting to the HTTP proxy."""
        # Replace the proxy with a TCP server that doesn't respond.
        with socket.create_server(("localhost", 0)) as sock:
            host, port = sock.getsockname()
            with patch.dict(os.environ, {"https_proxy": f"http://{host}:{port}"}):
                with self.assertRaises(TimeoutError) as raised:
                    async with connect("ws://example.com/", open_timeout=2 * MS):
                        self.fail("did not raise")
        self.assertEqual(
            str(raised.exception),
            "timed out during opening handshake",
        )

    @patch.dict(os.environ, {"https_proxy": "https://localhost:58080"})
    async def test_https_proxy(self):
        """Client connects to server through an HTTPS proxy."""
        async with run_server() as server:
            async with connect(
                get_uri(server),
                proxy_ssl=self.proxy_context,
            ) as client:
                self.assertEqual(client.protocol.state.name, "OPEN")
        self.assertNumFlows(1)

    @patch.dict(os.environ, {"https_proxy": "https://localhost:58080"})
    async def test_secure_https_proxy(self):
        """Client connects to server securely through an HTTPS proxy."""
        async with run_server(ssl=SERVER_CONTEXT) as server:
            async with connect(
                get_uri(server, secure=True),
                ssl=CLIENT_CONTEXT,
                proxy_ssl=self.proxy_context,
            ) as client:
                self.assertEqual(client.protocol.state.name, "OPEN")
                ssl_object = client.stream._ssl_object
                self.assertEqual(ssl_object.version()[:3], "TLS")
        self.assertNumFlows(1)

    @patch.dict(os.environ, {"https_proxy": "https://localhost:58080"})
    async def test_https_server_hostname(self):
        """Client sets server_hostname to the value of proxy_server_hostname."""
        async with run_server() as server:
            # Pass an argument not prefixed with proxy_ for coverage.
            kwargs = {"all_errors": True} if sys.version_info >= (3, 12) else {}
            async with connect(
                get_uri(server),
                proxy_ssl=self.proxy_context,
                proxy_server_hostname="overridden",
                **kwargs,
            ) as client:
                ssl_object = client.stream._ssl_object
                self.assertEqual(ssl_object.server_hostname, "overridden")
        self.assertNumFlows(1)

    @patch.dict(os.environ, {"https_proxy": "https://localhost:58080"})
    async def test_https_proxy_invalid_proxy_certificate(self):
        """Client rejects certificate when proxy certificate isn't trusted."""
        with self.assertRaises(trio.BrokenResourceError) as raised:
            # The proxy certificate isn't trusted.
            async with connect("wss://example.com/"):
                self.fail("did not raise")
        self.assertIsInstance(raised.exception.__cause__, ssl.SSLCertVerificationError)
        self.assertIn(
            "certificate verify failed: unable to get local issuer certificate",
            str(raised.exception.__cause__),
        )

    @patch.dict(os.environ, {"https_proxy": "https://localhost:58080"})
    async def test_https_proxy_invalid_server_certificate(self):
        """Client rejects certificate when proxy certificate isn't trusted."""
        async with run_server(ssl=SERVER_CONTEXT) as server:
            with self.assertRaises(trio.BrokenResourceError) as raised:
                # The test certificate is self-signed.
                async with connect(
                    get_uri(server, secure=True), proxy_ssl=self.proxy_context
                ):
                    self.fail("did not raise")
        self.assertIsInstance(raised.exception.__cause__, ssl.SSLCertVerificationError)
        self.assertIn(
            "certificate verify failed: self signed certificate",
            str(raised.exception.__cause__).replace("-", " "),
        )
        self.assertNumFlows(1)


class ClientUsageErrorsTests(IsolatedTrioTestCase):
    async def test_ssl_without_secure_uri(self):
        """Client rejects ssl when URI isn't secure."""
        with self.assertRaises(ValueError) as raised:
            async with connect("ws://localhost/", ssl=CLIENT_CONTEXT):
                self.fail("did not raise")
        self.assertEqual(
            str(raised.exception),
            "ssl argument is incompatible with a ws:// URI",
        )

    async def test_proxy_ssl_without_https_proxy(self):
        """Client rejects proxy_ssl when proxy isn't HTTPS."""
        with self.assertRaises(ValueError) as raised:
            async with connect(
                "ws://localhost/",
                proxy="http://localhost:8080",
                proxy_ssl=True,
            ):
                self.fail("did not raise")
        self.assertEqual(
            str(raised.exception),
            "proxy_ssl argument is incompatible with an http:// proxy",
        )

    async def test_unsupported_proxy(self):
        """Client rejects unsupported proxy."""
        with self.assertRaises(InvalidProxy) as raised:
            async with connect("ws://example.com/", proxy="other://localhost:51080"):
                self.fail("did not raise")
        self.assertEqual(
            str(raised.exception),
            "other://localhost:51080 isn't a valid proxy: scheme other isn't supported",
        )

    async def test_invalid_subprotocol(self):
        """Client rejects single value of subprotocols."""
        with self.assertRaises(TypeError) as raised:
            async with connect("ws://localhost/", subprotocols="chat"):
                self.fail("did not raise")
        self.assertEqual(
            str(raised.exception),
            "subprotocols must be a list, not a str",
        )

    async def test_unsupported_compression(self):
        """Client rejects incorrect value of compression."""
        with self.assertRaises(ValueError) as raised:
            async with connect("ws://localhost/", compression=False):
                self.fail("did not raise")
        self.assertEqual(
            str(raised.exception),
            "unsupported compression: False",
        )

    async def test_reentrancy(self):
        """Client isn't reentrant."""
        async with run_server() as server:
            connecter = connect(get_uri(server))
            async with connecter:
                with self.assertRaises(RuntimeError) as raised:
                    async with connecter:
                        self.fail("did not raise")
        self.assertEqual(
            str(raised.exception),
            "connect() isn't reentrant",
        )
