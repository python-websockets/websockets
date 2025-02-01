import http
import logging
import os
import socket
import socketserver
import ssl
import sys
import threading
import time
import unittest
from unittest.mock import patch

from websockets.exceptions import (
    InvalidHandshake,
    InvalidMessage,
    InvalidProxy,
    InvalidProxyMessage,
    InvalidStatus,
    InvalidURI,
    ProxyError,
)
from websockets.extensions.permessage_deflate import PerMessageDeflate
from websockets.sync.client import *

from ..proxy import ProxyMixin
from ..utils import (
    CLIENT_CONTEXT,
    MS,
    SERVER_CONTEXT,
    DeprecationTestCase,
    temp_unix_socket_path,
)
from .server import get_uri, run_server, run_unix_server


class ClientTests(unittest.TestCase):
    def test_connection(self):
        """Client connects to server and the handshake succeeds."""
        with run_server() as server:
            with connect(get_uri(server)) as client:
                self.assertEqual(client.protocol.state.name, "OPEN")

    def test_existing_socket(self):
        """Client connects using a pre-existing socket."""
        with run_server() as server:
            with socket.create_connection(server.socket.getsockname()) as sock:
                # Use a non-existing domain to ensure we connect to sock.
                with connect("ws://invalid/", sock=sock) as client:
                    self.assertEqual(client.protocol.state.name, "OPEN")

    def test_compression_is_enabled(self):
        """Client enables compression by default."""
        with run_server() as server:
            with connect(get_uri(server)) as client:
                self.assertEqual(
                    [type(ext) for ext in client.protocol.extensions],
                    [PerMessageDeflate],
                )

    def test_disable_compression(self):
        """Client disables compression."""
        with run_server() as server:
            with connect(get_uri(server), compression=None) as client:
                self.assertEqual(client.protocol.extensions, [])

    def test_additional_headers(self):
        """Client can set additional headers with additional_headers."""
        with run_server() as server:
            with connect(
                get_uri(server), additional_headers={"Authorization": "Bearer ..."}
            ) as client:
                self.assertEqual(client.request.headers["Authorization"], "Bearer ...")

    def test_override_user_agent(self):
        """Client can override User-Agent header with user_agent_header."""
        with run_server() as server:
            with connect(get_uri(server), user_agent_header="Smith") as client:
                self.assertEqual(client.request.headers["User-Agent"], "Smith")

    def test_remove_user_agent(self):
        """Client can remove User-Agent header with user_agent_header."""
        with run_server() as server:
            with connect(get_uri(server), user_agent_header=None) as client:
                self.assertNotIn("User-Agent", client.request.headers)

    def test_legacy_user_agent(self):
        """Client can override User-Agent header with additional_headers."""
        with run_server() as server:
            with connect(
                get_uri(server), additional_headers={"User-Agent": "Smith"}
            ) as client:
                self.assertEqual(client.request.headers["User-Agent"], "Smith")

    def test_keepalive_is_enabled(self):
        """Client enables keepalive and measures latency by default."""
        with run_server() as server:
            with connect(get_uri(server), ping_interval=MS) as client:
                self.assertEqual(client.latency, 0)
                time.sleep(2 * MS)
                self.assertGreater(client.latency, 0)

    def test_disable_keepalive(self):
        """Client disables keepalive."""
        with run_server() as server:
            with connect(get_uri(server), ping_interval=None) as client:
                time.sleep(2 * MS)
                self.assertEqual(client.latency, 0)

    def test_logger(self):
        """Client accepts a logger argument."""
        logger = logging.getLogger("test")
        with run_server() as server:
            with connect(get_uri(server), logger=logger) as client:
                self.assertEqual(client.logger.name, logger.name)

    def test_custom_connection_factory(self):
        """Client runs ClientConnection factory provided in create_connection."""

        def create_connection(*args, **kwargs):
            client = ClientConnection(*args, **kwargs)
            client.create_connection_ran = True
            return client

        with run_server() as server:
            with connect(
                get_uri(server), create_connection=create_connection
            ) as client:
                self.assertTrue(client.create_connection_ran)

    def test_invalid_uri(self):
        """Client receives an invalid URI."""
        with self.assertRaises(InvalidURI):
            with connect("http://localhost"):  # invalid scheme
                self.fail("did not raise")

    def test_tcp_connection_fails(self):
        """Client fails to connect to server."""
        with self.assertRaises(OSError):
            with connect("ws://localhost:54321"):  # invalid port
                self.fail("did not raise")

    def test_handshake_fails(self):
        """Client connects to server but the handshake fails."""

        def remove_accept_header(self, request, response):
            del response.headers["Sec-WebSocket-Accept"]

        # The connection will be open for the server but failed for the client.
        # Use a connection handler that exits immediately to avoid an exception.
        with run_server(process_response=remove_accept_header) as server:
            with self.assertRaises(InvalidHandshake) as raised:
                with connect(get_uri(server) + "/no-op", close_timeout=MS):
                    self.fail("did not raise")
            self.assertEqual(
                str(raised.exception),
                "missing Sec-WebSocket-Accept header",
            )

    def test_timeout_during_handshake(self):
        """Client times out before receiving handshake response from server."""
        # Replace the WebSocket server with a TCP server that doesn't respond.
        with socket.create_server(("localhost", 0)) as sock:
            host, port = sock.getsockname()
            with self.assertRaises(TimeoutError) as raised:
                with connect(f"ws://{host}:{port}", open_timeout=MS):
                    self.fail("did not raise")
            self.assertEqual(
                str(raised.exception),
                "timed out while waiting for handshake response",
            )

    def test_connection_closed_during_handshake(self):
        """Client reads EOF before receiving handshake response from server."""

        def close_connection(self, request):
            self.socket.shutdown(socket.SHUT_RDWR)
            self.socket.close()

        with run_server(process_request=close_connection) as server:
            with self.assertRaises(InvalidMessage) as raised:
                with connect(get_uri(server)):
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

    def test_http_response(self):
        """Client reads HTTP response."""

        def http_response(connection, request):
            return connection.respond(http.HTTPStatus.OK, "👌")

        with run_server(process_request=http_response) as server:
            with self.assertRaises(InvalidStatus) as raised:
                with connect(get_uri(server)):
                    self.fail("did not raise")

        self.assertEqual(raised.exception.response.status_code, 200)
        self.assertEqual(raised.exception.response.body.decode(), "👌")

    def test_http_response_without_content_length(self):
        """Client reads HTTP response without a Content-Length header."""

        def http_response(connection, request):
            response = connection.respond(http.HTTPStatus.OK, "👌")
            del response.headers["Content-Length"]
            return response

        with run_server(process_request=http_response) as server:
            with self.assertRaises(InvalidStatus) as raised:
                with connect(get_uri(server)):
                    self.fail("did not raise")

        self.assertEqual(raised.exception.response.status_code, 200)
        self.assertEqual(raised.exception.response.body.decode(), "👌")

    def test_junk_handshake(self):
        """Client closes the connection when receiving non-HTTP response from server."""

        class JunkHandler(socketserver.BaseRequestHandler):
            def handle(self):
                time.sleep(MS)  # wait for the client to send the handshake request
                self.request.send(b"220 smtp.invalid ESMTP Postfix\r\n")
                self.request.recv(4096)  # wait for the client to close the connection
                self.request.close()

        server = socketserver.TCPServer(("localhost", 0), JunkHandler)
        host, port = server.server_address
        with server:
            thread = threading.Thread(target=server.serve_forever, args=(MS,))
            thread.start()
            try:
                with self.assertRaises(InvalidMessage) as raised:
                    with connect(f"ws://{host}:{port}"):
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
                server.shutdown()
                thread.join()


class SecureClientTests(unittest.TestCase):
    def test_connection(self):
        """Client connects to server securely."""
        with run_server(ssl=SERVER_CONTEXT) as server:
            with connect(get_uri(server), ssl=CLIENT_CONTEXT) as client:
                self.assertEqual(client.protocol.state.name, "OPEN")
                self.assertEqual(client.socket.version()[:3], "TLS")

    def test_set_server_hostname_implicitly(self):
        """Client sets server_hostname to the host in the WebSocket URI."""
        with temp_unix_socket_path() as path:
            with run_unix_server(path, ssl=SERVER_CONTEXT):
                with unix_connect(
                    path, ssl=CLIENT_CONTEXT, uri="wss://overridden/"
                ) as client:
                    self.assertEqual(client.socket.server_hostname, "overridden")

    def test_set_server_hostname_explicitly(self):
        """Client sets server_hostname to the value provided in argument."""
        with temp_unix_socket_path() as path:
            with run_unix_server(path, ssl=SERVER_CONTEXT):
                with unix_connect(
                    path, ssl=CLIENT_CONTEXT, server_hostname="overridden"
                ) as client:
                    self.assertEqual(client.socket.server_hostname, "overridden")

    def test_reject_invalid_server_certificate(self):
        """Client rejects certificate where server certificate isn't trusted."""
        with run_server(ssl=SERVER_CONTEXT) as server:
            with self.assertRaises(ssl.SSLCertVerificationError) as raised:
                # The test certificate is self-signed.
                with connect(get_uri(server)):
                    self.fail("did not raise")
            self.assertIn(
                "certificate verify failed: self signed certificate",
                str(raised.exception).replace("-", " "),
            )

    def test_reject_invalid_server_hostname(self):
        """Client rejects certificate where server hostname doesn't match."""
        with run_server(ssl=SERVER_CONTEXT) as server:
            with self.assertRaises(ssl.SSLCertVerificationError) as raised:
                # This hostname isn't included in the test certificate.
                with connect(
                    get_uri(server), ssl=CLIENT_CONTEXT, server_hostname="invalid"
                ):
                    self.fail("did not raise")
            self.assertIn(
                "certificate verify failed: Hostname mismatch",
                str(raised.exception),
            )


@unittest.skipUnless("mitmproxy" in sys.modules, "mitmproxy not installed")
class SocksProxyClientTests(ProxyMixin, unittest.TestCase):
    proxy_mode = "socks5@51080"

    @patch.dict(os.environ, {"socks_proxy": "http://localhost:51080"})
    def test_socks_proxy(self):
        """Client connects to server through a SOCKS5 proxy."""
        with run_server() as server:
            with connect(get_uri(server)) as client:
                self.assertEqual(client.protocol.state.name, "OPEN")
        self.assertNumFlows(1)

    @patch.dict(os.environ, {"socks_proxy": "http://localhost:51080"})
    def test_secure_socks_proxy(self):
        """Client connects to server securely through a SOCKS5 proxy."""
        with run_server(ssl=SERVER_CONTEXT) as server:
            with connect(get_uri(server), ssl=CLIENT_CONTEXT) as client:
                self.assertEqual(client.protocol.state.name, "OPEN")
        self.assertNumFlows(1)

    @patch.dict(os.environ, {"socks_proxy": "http://hello:iloveyou@localhost:51080"})
    def test_authenticated_socks_proxy(self):
        """Client connects to server through an authenticated SOCKS5 proxy."""
        try:
            self.proxy_options.update(proxyauth="hello:iloveyou")
            with run_server() as server:
                with connect(get_uri(server)) as client:
                    self.assertEqual(client.protocol.state.name, "OPEN")
        finally:
            self.proxy_options.update(proxyauth=None)
        self.assertNumFlows(1)

    @patch.dict(os.environ, {"socks_proxy": "http://localhost:51080"})
    def test_authenticated_socks_proxy_error(self):
        """Client fails to authenticate to the SOCKS5 proxy."""
        from python_socks import ProxyError as SocksProxyError

        try:
            self.proxy_options.update(proxyauth="any")
            with self.assertRaises(ProxyError) as raised:
                with connect("ws://example.com/"):
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
    def test_socks_proxy_connection_failure(self):
        """Client fails to connect to the SOCKS5 proxy."""
        from python_socks import ProxyConnectionError as SocksProxyConnectionError

        with self.assertRaises(OSError) as raised:
            with connect("ws://example.com/"):
                self.fail("did not raise")
        # Don't test str(raised.exception) because we don't control it.
        self.assertIsInstance(raised.exception, SocksProxyConnectionError)
        self.assertNumFlows(0)

    def test_socks_proxy_connection_timeout(self):
        """Client times out while connecting to the SOCKS5 proxy."""
        from python_socks import ProxyTimeoutError as SocksProxyTimeoutError

        # Replace the proxy with a TCP server that doesn't respond.
        with socket.create_server(("localhost", 0)) as sock:
            host, port = sock.getsockname()
            with patch.dict(os.environ, {"socks_proxy": f"http://{host}:{port}"}):
                with self.assertRaises(TimeoutError) as raised:
                    with connect("ws://example.com/", open_timeout=MS):
                        self.fail("did not raise")
        # Don't test str(raised.exception) because we don't control it.
        self.assertIsInstance(raised.exception, SocksProxyTimeoutError)
        self.assertNumFlows(0)

    def test_explicit_socks_proxy(self):
        """Client connects to server through a SOCKS5 proxy set explicitly."""
        with run_server() as server:
            with connect(
                get_uri(server),
                # Take this opportunity to test socks5 instead of socks5h.
                proxy="socks5://localhost:51080",
            ) as client:
                self.assertEqual(client.protocol.state.name, "OPEN")
        self.assertNumFlows(1)

    @patch.dict(os.environ, {"ws_proxy": "http://localhost:58080"})
    def test_ignore_proxy_with_existing_socket(self):
        """Client connects using a pre-existing socket."""
        with run_server() as server:
            with socket.create_connection(server.socket.getsockname()) as sock:
                # Use a non-existing domain to ensure we connect to sock.
                with connect("ws://invalid/", sock=sock) as client:
                    self.assertEqual(client.protocol.state.name, "OPEN")
        self.assertNumFlows(0)


@unittest.skipUnless("mitmproxy" in sys.modules, "mitmproxy not installed")
class HTTPProxyClientTests(ProxyMixin, unittest.IsolatedAsyncioTestCase):
    proxy_mode = "regular@58080"

    @patch.dict(os.environ, {"https_proxy": "http://localhost:58080"})
    def test_http_proxy(self):
        """Client connects to server through an HTTP proxy."""
        with run_server() as server:
            with connect(get_uri(server)) as client:
                self.assertEqual(client.protocol.state.name, "OPEN")
        self.assertNumFlows(1)

    @patch.dict(os.environ, {"https_proxy": "http://localhost:58080"})
    def test_secure_http_proxy(self):
        """Client connects to server securely through an HTTP proxy."""
        with run_server(ssl=SERVER_CONTEXT) as server:
            with connect(get_uri(server), ssl=CLIENT_CONTEXT) as client:
                self.assertEqual(client.protocol.state.name, "OPEN")
                self.assertEqual(client.socket.version()[:3], "TLS")
        self.assertNumFlows(1)

    @patch.dict(os.environ, {"https_proxy": "http://hello:iloveyou@localhost:58080"})
    def test_authenticated_http_proxy(self):
        """Client connects to server through an authenticated HTTP proxy."""
        try:
            self.proxy_options.update(proxyauth="hello:iloveyou")
            with run_server() as server:
                with connect(get_uri(server)) as client:
                    self.assertEqual(client.protocol.state.name, "OPEN")
        finally:
            self.proxy_options.update(proxyauth=None)
        self.assertNumFlows(1)

    @patch.dict(os.environ, {"https_proxy": "http://localhost:58080"})
    def test_authenticated_http_proxy_error(self):
        """Client fails to authenticate to the HTTP proxy."""
        try:
            self.proxy_options.update(proxyauth="any")
            with self.assertRaises(ProxyError) as raised:
                with connect("ws://example.com/"):
                    self.fail("did not raise")
        finally:
            self.proxy_options.update(proxyauth=None)
        self.assertEqual(
            str(raised.exception),
            "proxy rejected connection: HTTP 407",
        )
        self.assertNumFlows(0)

    @patch.dict(os.environ, {"https_proxy": "http://localhost:58080"})
    def test_http_proxy_override_user_agent(self):
        """Client can override User-Agent header with user_agent_header."""
        with run_server() as server:
            with connect(get_uri(server), user_agent_header="Smith") as client:
                self.assertEqual(client.protocol.state.name, "OPEN")
        [http_connect] = self.get_http_connects()
        self.assertEqual(http_connect.request.headers[b"User-Agent"], "Smith")

    @patch.dict(os.environ, {"https_proxy": "http://localhost:58080"})
    def test_http_proxy_remove_user_agent(self):
        """Client can remove User-Agent header with user_agent_header."""
        with run_server() as server:
            with connect(get_uri(server), user_agent_header=None) as client:
                self.assertEqual(client.protocol.state.name, "OPEN")
        [http_connect] = self.get_http_connects()
        self.assertNotIn(b"User-Agent", http_connect.request.headers)

    @patch.dict(os.environ, {"https_proxy": "http://localhost:58080"})
    def test_http_proxy_protocol_error(self):
        """Client receives invalid data when connecting to the HTTP proxy."""
        try:
            self.proxy_options.update(break_http_connect=True)
            with self.assertRaises(InvalidProxyMessage) as raised:
                with connect("ws://example.com/"):
                    self.fail("did not raise")
        finally:
            self.proxy_options.update(break_http_connect=False)
        self.assertEqual(
            str(raised.exception),
            "did not receive a valid HTTP response from proxy",
        )
        self.assertNumFlows(0)

    @patch.dict(os.environ, {"https_proxy": "http://localhost:58080"})
    def test_http_proxy_connection_error(self):
        """Client receives no response when connecting to the HTTP proxy."""
        try:
            self.proxy_options.update(close_http_connect=True)
            with self.assertRaises(InvalidProxyMessage) as raised:
                with connect("ws://example.com/"):
                    self.fail("did not raise")
        finally:
            self.proxy_options.update(close_http_connect=False)
        self.assertEqual(
            str(raised.exception),
            "did not receive a valid HTTP response from proxy",
        )
        self.assertNumFlows(0)

    @patch.dict(os.environ, {"https_proxy": "http://localhost:48080"})  # bad port
    def test_http_proxy_connection_failure(self):
        """Client fails to connect to the HTTP proxy."""
        with self.assertRaises(OSError):
            with connect("ws://example.com/"):
                self.fail("did not raise")
        # Don't test str(raised.exception) because we don't control it.
        self.assertNumFlows(0)

    def test_http_proxy_connection_timeout(self):
        """Client times out while connecting to the HTTP proxy."""
        # Replace the proxy with a TCP server that does't respond.
        with socket.create_server(("localhost", 0)) as sock:
            host, port = sock.getsockname()
            with patch.dict(os.environ, {"https_proxy": f"http://{host}:{port}"}):
                with self.assertRaises(TimeoutError) as raised:
                    with connect("ws://example.com/", open_timeout=MS):
                        self.fail("did not raise")
        self.assertEqual(
            str(raised.exception),
            "timed out while connecting to HTTP proxy",
        )

    @patch.dict(os.environ, {"https_proxy": "https://localhost:58080"})
    def test_https_proxy(self):
        """Client connects to server through an HTTPS proxy."""
        with run_server() as server:
            with connect(
                get_uri(server),
                proxy_ssl=self.proxy_context,
            ) as client:
                self.assertEqual(client.protocol.state.name, "OPEN")
        self.assertNumFlows(1)

    @patch.dict(os.environ, {"https_proxy": "https://localhost:58080"})
    def test_secure_https_proxy(self):
        """Client connects to server securely through an HTTPS proxy."""
        with run_server(ssl=SERVER_CONTEXT) as server:
            with connect(
                get_uri(server),
                ssl=CLIENT_CONTEXT,
                proxy_ssl=self.proxy_context,
            ) as client:
                self.assertEqual(client.protocol.state.name, "OPEN")
                self.assertEqual(client.socket.version()[:3], "TLS")
        self.assertNumFlows(1)

    @patch.dict(os.environ, {"https_proxy": "https://localhost:58080"})
    def test_https_proxy_server_hostname(self):
        """Client sets server_hostname to the value of proxy_server_hostname."""
        with run_server() as server:
            # Pass an argument not prefixed with proxy_ for coverage.
            kwargs = {"all_errors": True} if sys.version_info >= (3, 11) else {}
            with connect(
                get_uri(server),
                proxy_ssl=self.proxy_context,
                proxy_server_hostname="overridden",
                **kwargs,
            ) as client:
                self.assertEqual(client.socket.server_hostname, "overridden")
        self.assertNumFlows(1)

    @patch.dict(os.environ, {"https_proxy": "https://localhost:58080"})
    def test_https_proxy_invalid_proxy_certificate(self):
        """Client rejects certificate when proxy certificate isn't trusted."""
        with self.assertRaises(ssl.SSLCertVerificationError) as raised:
            # The proxy certificate isn't trusted.
            with connect("wss://example.com/"):
                self.fail("did not raise")
        self.assertIn(
            "certificate verify failed: unable to get local issuer certificate",
            str(raised.exception),
        )
        self.assertNumFlows(0)

    @patch.dict(os.environ, {"https_proxy": "https://localhost:58080"})
    def test_https_proxy_invalid_server_certificate(self):
        """Client rejects certificate when server certificate isn't trusted."""
        with run_server(ssl=SERVER_CONTEXT) as server:
            with self.assertRaises(ssl.SSLCertVerificationError) as raised:
                # The test certificate is self-signed.
                with connect(get_uri(server), proxy_ssl=self.proxy_context):
                    self.fail("did not raise")
        self.assertIn(
            "certificate verify failed: self signed certificate",
            str(raised.exception).replace("-", " "),
        )
        self.assertNumFlows(1)


@unittest.skipUnless(hasattr(socket, "AF_UNIX"), "this test requires Unix sockets")
class UnixClientTests(unittest.TestCase):
    def test_connection(self):
        """Client connects to server over a Unix socket."""
        with temp_unix_socket_path() as path:
            with run_unix_server(path):
                with unix_connect(path) as client:
                    self.assertEqual(client.protocol.state.name, "OPEN")

    def test_set_host_header(self):
        """Client sets the Host header to the host in the WebSocket URI."""
        # This is part of the documented behavior of unix_connect().
        with temp_unix_socket_path() as path:
            with run_unix_server(path):
                with unix_connect(path, uri="ws://overridden/") as client:
                    self.assertEqual(client.request.headers["Host"], "overridden")

    def test_secure_connection(self):
        """Client connects to server securely over a Unix socket."""
        with temp_unix_socket_path() as path:
            with run_unix_server(path, ssl=SERVER_CONTEXT):
                with unix_connect(path, ssl=CLIENT_CONTEXT) as client:
                    self.assertEqual(client.protocol.state.name, "OPEN")
                    self.assertEqual(client.socket.version()[:3], "TLS")

    def test_set_server_hostname(self):
        """Client sets server_hostname to the host in the WebSocket URI."""
        # This is part of the documented behavior of unix_connect().
        with temp_unix_socket_path() as path:
            with run_unix_server(path, ssl=SERVER_CONTEXT):
                with unix_connect(
                    path, ssl=CLIENT_CONTEXT, uri="wss://overridden/"
                ) as client:
                    self.assertEqual(client.socket.server_hostname, "overridden")


class ClientUsageErrorsTests(unittest.TestCase):
    def test_ssl_without_secure_uri(self):
        """Client rejects ssl when URI isn't secure."""
        with self.assertRaises(ValueError) as raised:
            connect("ws://localhost/", ssl=CLIENT_CONTEXT)
        self.assertEqual(
            str(raised.exception),
            "ssl argument is incompatible with a ws:// URI",
        )

    def test_proxy_ssl_without_https_proxy(self):
        """Client rejects proxy_ssl when proxy isn't HTTPS."""
        with self.assertRaises(ValueError) as raised:
            connect(
                "ws://localhost/",
                proxy="http://localhost:8080",
                proxy_ssl=True,
            )
        self.assertEqual(
            str(raised.exception),
            "proxy_ssl argument is incompatible with an http:// proxy",
        )

    def test_unix_without_path_or_sock(self):
        """Unix client requires path when sock isn't provided."""
        with self.assertRaises(ValueError) as raised:
            unix_connect()
        self.assertEqual(
            str(raised.exception),
            "missing path argument",
        )

    def test_unsupported_proxy(self):
        """Client rejects unsupported proxy."""
        with self.assertRaises(InvalidProxy) as raised:
            with connect("ws://example.com/", proxy="other://localhost:58080"):
                self.fail("did not raise")
        self.assertEqual(
            str(raised.exception),
            "other://localhost:58080 isn't a valid proxy: scheme other isn't supported",
        )

    def test_unix_with_path_and_sock(self):
        """Unix client rejects path when sock is provided."""
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.addCleanup(sock.close)
        with self.assertRaises(ValueError) as raised:
            unix_connect(path="/", sock=sock)
        self.assertEqual(
            str(raised.exception),
            "path and sock arguments are incompatible",
        )

    def test_invalid_subprotocol(self):
        """Client rejects single value of subprotocols."""
        with self.assertRaises(TypeError) as raised:
            connect("ws://localhost/", subprotocols="chat")
        self.assertEqual(
            str(raised.exception),
            "subprotocols must be a list, not a str",
        )

    def test_unsupported_compression(self):
        """Client rejects incorrect value of compression."""
        with self.assertRaises(ValueError) as raised:
            connect("ws://localhost/", compression=False)
        self.assertEqual(
            str(raised.exception),
            "unsupported compression: False",
        )


class BackwardsCompatibilityTests(DeprecationTestCase):
    def test_ssl_context_argument(self):
        """Client supports the deprecated ssl_context argument."""
        with run_server(ssl=SERVER_CONTEXT) as server:
            with self.assertDeprecationWarning("ssl_context was renamed to ssl"):
                with connect(get_uri(server), ssl_context=CLIENT_CONTEXT):
                    pass
