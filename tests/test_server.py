import http
import logging
import sys
import unittest
from unittest.mock import patch

from websockets.datastructures import Headers
from websockets.exceptions import (
    InvalidHeader,
    InvalidOrigin,
    InvalidUpgrade,
    NegotiationError,
)
from websockets.frames import OP_TEXT, Frame
from websockets.http11 import Request, Response
from websockets.protocol import CONNECTING, OPEN
from websockets.server import *

from .extensions.utils import (
    OpExtension,
    Rsv2Extension,
    ServerOpExtensionFactory,
    ServerRsv2ExtensionFactory,
)
from .test_utils import ACCEPT, KEY
from .utils import DATE, DeprecationTestCase


def make_request():
    """Generate a handshake request that can be altered for testing."""
    return Request(
        path="/test",
        headers=Headers(
            {
                "Host": "example.com",
                "Upgrade": "websocket",
                "Connection": "Upgrade",
                "Sec-WebSocket-Key": KEY,
                "Sec-WebSocket-Version": "13",
            }
        ),
    )


@patch("email.utils.formatdate", return_value=DATE)
class BasicTests(unittest.TestCase):
    """Test basic opening handshake scenarios."""

    def test_receive_request(self, _formatdate):
        """Server receives a handshake request."""
        server = ServerProtocol()
        server.receive_data(
            (
                f"GET /test HTTP/1.1\r\n"
                f"Host: example.com\r\n"
                f"Upgrade: websocket\r\n"
                f"Connection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {KEY}\r\n"
                f"Sec-WebSocket-Version: 13\r\n"
                f"\r\n"
            ).encode(),
        )

        self.assertEqual(server.data_to_send(), [])
        self.assertFalse(server.close_expected())
        self.assertEqual(server.state, CONNECTING)

    def test_accept_and_send_successful_response(self, _formatdate):
        """Server accepts a handshake request and sends a successful response."""
        server = ServerProtocol()
        request = make_request()
        response = server.accept(request)
        server.send_response(response)

        self.assertEqual(
            server.data_to_send(),
            [
                f"HTTP/1.1 101 Switching Protocols\r\n"
                f"Date: {DATE}\r\n"
                f"Upgrade: websocket\r\n"
                f"Connection: Upgrade\r\n"
                f"Sec-WebSocket-Accept: {ACCEPT}\r\n"
                f"\r\n".encode()
            ],
        )
        self.assertFalse(server.close_expected())
        self.assertEqual(server.state, OPEN)

    def test_send_response_after_failed_accept(self, _formatdate):
        """Server accepts a handshake request but sends a failed response."""
        server = ServerProtocol()
        request = make_request()
        del request.headers["Sec-WebSocket-Key"]
        response = server.accept(request)
        server.send_response(response)

        self.assertEqual(
            server.data_to_send(),
            [
                f"HTTP/1.1 400 Bad Request\r\n"
                f"Date: {DATE}\r\n"
                f"Connection: close\r\n"
                f"Content-Length: 73\r\n"
                f"Content-Type: text/plain; charset=utf-8\r\n"
                f"\r\n"
                f"Failed to open a WebSocket connection: "
                f"missing Sec-WebSocket-Key header.\n".encode(),
                b"",
            ],
        )
        self.assertTrue(server.close_expected())
        self.assertEqual(server.state, CONNECTING)

    def test_send_response_after_reject(self, _formatdate):
        """Server rejects a handshake request and sends a failed response."""
        server = ServerProtocol()
        response = server.reject(http.HTTPStatus.NOT_FOUND, "Sorry folks.\n")
        server.send_response(response)

        self.assertEqual(
            server.data_to_send(),
            [
                f"HTTP/1.1 404 Not Found\r\n"
                f"Date: {DATE}\r\n"
                f"Connection: close\r\n"
                f"Content-Length: 13\r\n"
                f"Content-Type: text/plain; charset=utf-8\r\n"
                f"\r\n"
                f"Sorry folks.\n".encode(),
                b"",
            ],
        )
        self.assertTrue(server.close_expected())
        self.assertEqual(server.state, CONNECTING)

    def test_send_response_without_accept_or_reject(self, _formatdate):
        """Server doesn't accept or reject and sends a failed response."""
        server = ServerProtocol()
        server.send_response(
            Response(
                410,
                "Gone",
                Headers(
                    {
                        "Connection": "close",
                        "Content-Length": 6,
                        "Content-Type": "text/plain",
                    }
                ),
                b"AWOL.\n",
            )
        )
        self.assertEqual(
            server.data_to_send(),
            [
                "HTTP/1.1 410 Gone\r\n"
                "Connection: close\r\n"
                "Content-Length: 6\r\n"
                "Content-Type: text/plain\r\n"
                "\r\n"
                "AWOL.\n".encode(),
                b"",
            ],
        )
        self.assertTrue(server.close_expected())
        self.assertEqual(server.state, CONNECTING)


class RequestTests(unittest.TestCase):
    """Test receiving opening handshake requests."""

    def test_receive_request(self):
        """Server receives a handshake request."""
        server = ServerProtocol()
        server.receive_data(
            (
                f"GET /test HTTP/1.1\r\n"
                f"Host: example.com\r\n"
                f"Upgrade: websocket\r\n"
                f"Connection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {KEY}\r\n"
                f"Sec-WebSocket-Version: 13\r\n"
                f"\r\n"
            ).encode(),
        )
        [request] = server.events_received()

        self.assertIsInstance(request, Request)
        self.assertEqual(request.path, "/test")
        self.assertEqual(
            request.headers,
            Headers(
                {
                    "Host": "example.com",
                    "Upgrade": "websocket",
                    "Connection": "Upgrade",
                    "Sec-WebSocket-Key": KEY,
                    "Sec-WebSocket-Version": "13",
                }
            ),
        )
        self.assertIsNone(server.handshake_exc)

    def test_receive_no_request(self):
        """Server receives no handshake request."""
        server = ServerProtocol()
        server.receive_eof()

        self.assertEqual(server.events_received(), [])
        self.assertIsInstance(server.handshake_exc, EOFError)
        self.assertEqual(
            str(server.handshake_exc),
            "connection closed while reading HTTP request line",
        )

    def test_receive_truncated_request(self):
        """Server receives a truncated handshake request."""
        server = ServerProtocol()
        server.receive_data(b"GET /test HTTP/1.1\r\n")
        server.receive_eof()

        self.assertEqual(server.events_received(), [])
        self.assertIsInstance(server.handshake_exc, EOFError)
        self.assertEqual(
            str(server.handshake_exc),
            "connection closed while reading HTTP headers",
        )

    def test_receive_junk_request(self):
        """Server receives a junk handshake request."""
        server = ServerProtocol()
        server.receive_data(b"HELO relay.invalid\r\n")
        server.receive_data(b"MAIL FROM: <alice@invalid>\r\n")
        server.receive_data(b"RCPT TO: <bob@invalid>\r\n")

        self.assertEqual(server.events_received(), [])
        self.assertIsInstance(server.handshake_exc, ValueError)
        self.assertEqual(
            str(server.handshake_exc),
            "invalid HTTP request line: HELO relay.invalid",
        )


class ResponseTests(unittest.TestCase):
    """Test generating opening handshake responses."""

    @patch("email.utils.formatdate", return_value=DATE)
    def test_accept_response(self, _formatdate):
        """accept() creates a successful opening handshake response."""
        server = ServerProtocol()
        request = make_request()
        response = server.accept(request)

        self.assertIsInstance(response, Response)
        self.assertEqual(response.status_code, 101)
        self.assertEqual(response.reason_phrase, "Switching Protocols")
        self.assertEqual(
            response.headers,
            Headers(
                {
                    "Date": DATE,
                    "Upgrade": "websocket",
                    "Connection": "Upgrade",
                    "Sec-WebSocket-Accept": ACCEPT,
                }
            ),
        )
        self.assertIsNone(response.body)

    @patch("email.utils.formatdate", return_value=DATE)
    def test_reject_response(self, _formatdate):
        """reject() creates a failed opening handshake response."""
        server = ServerProtocol()
        response = server.reject(http.HTTPStatus.NOT_FOUND, "Sorry folks.\n")

        self.assertIsInstance(response, Response)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.reason_phrase, "Not Found")
        self.assertEqual(
            response.headers,
            Headers(
                {
                    "Date": DATE,
                    "Connection": "close",
                    "Content-Length": "13",
                    "Content-Type": "text/plain; charset=utf-8",
                }
            ),
        )
        self.assertEqual(response.body, b"Sorry folks.\n")

    def test_reject_response_supports_int_status(self):
        """reject() accepts an integer status code instead of an HTTPStatus."""
        server = ServerProtocol()
        response = server.reject(404, "Sorry folks.\n")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.reason_phrase, "Not Found")

    @patch("websockets.server.ServerProtocol.process_request")
    def test_unexpected_error(self, process_request):
        """accept() handles unexpected errors and returns an error response."""
        server = ServerProtocol()
        request = make_request()
        process_request.side_effect = (Exception("BOOM"),)
        response = server.accept(request)

        self.assertEqual(response.status_code, 500)
        self.assertIsInstance(server.handshake_exc, Exception)
        self.assertEqual(str(server.handshake_exc), "BOOM")


class HandshakeTests(unittest.TestCase):
    """Test processing of handshake responses to configure the connection."""

    def assertHandshakeSuccess(self, server):
        """Assert that the opening handshake succeeded."""
        self.assertEqual(server.state, OPEN)
        self.assertIsNone(server.handshake_exc)

    def assertHandshakeError(self, server, exc_type, msg):
        """Assert that the opening handshake failed with the given exception."""
        self.assertEqual(server.state, CONNECTING)
        self.assertIsInstance(server.handshake_exc, exc_type)
        exc = server.handshake_exc
        exc_str = str(exc)
        while exc.__cause__ is not None:
            exc = exc.__cause__
            exc_str += "; " + str(exc)
        self.assertEqual(exc_str, msg)

    def test_basic(self):
        """Handshake succeeds."""
        server = ServerProtocol()
        request = make_request()
        response = server.accept(request)
        server.send_response(response)

        self.assertHandshakeSuccess(server)

    def test_missing_connection(self):
        """Handshake fails when the Connection header is missing."""
        server = ServerProtocol()
        request = make_request()
        del request.headers["Connection"]
        response = server.accept(request)
        server.send_response(response)

        self.assertEqual(response.status_code, 426)
        self.assertEqual(response.headers["Upgrade"], "websocket")
        self.assertHandshakeError(
            server,
            InvalidUpgrade,
            "missing Connection header",
        )

    def test_invalid_connection(self):
        """Handshake fails when the Connection header is invalid."""
        server = ServerProtocol()
        request = make_request()
        del request.headers["Connection"]
        request.headers["Connection"] = "close"
        response = server.accept(request)
        server.send_response(response)

        self.assertEqual(response.status_code, 426)
        self.assertEqual(response.headers["Upgrade"], "websocket")
        self.assertHandshakeError(
            server,
            InvalidUpgrade,
            "invalid Connection header: close",
        )

    def test_missing_upgrade(self):
        """Handshake fails when the Upgrade header is missing."""
        server = ServerProtocol()
        request = make_request()
        del request.headers["Upgrade"]
        response = server.accept(request)
        server.send_response(response)

        self.assertEqual(response.status_code, 426)
        self.assertEqual(response.headers["Upgrade"], "websocket")
        self.assertHandshakeError(
            server,
            InvalidUpgrade,
            "missing Upgrade header",
        )

    def test_invalid_upgrade(self):
        """Handshake fails when the Upgrade header is invalid."""
        server = ServerProtocol()
        request = make_request()
        del request.headers["Upgrade"]
        request.headers["Upgrade"] = "h2c"
        response = server.accept(request)
        server.send_response(response)

        self.assertEqual(response.status_code, 426)
        self.assertEqual(response.headers["Upgrade"], "websocket")
        self.assertHandshakeError(
            server,
            InvalidUpgrade,
            "invalid Upgrade header: h2c",
        )

    def test_missing_key(self):
        """Handshake fails when the Sec-WebSocket-Key header is missing."""
        server = ServerProtocol()
        request = make_request()
        del request.headers["Sec-WebSocket-Key"]
        response = server.accept(request)
        server.send_response(response)

        self.assertEqual(response.status_code, 400)
        self.assertHandshakeError(
            server,
            InvalidHeader,
            "missing Sec-WebSocket-Key header",
        )

    def test_multiple_key(self):
        """Handshake fails when the Sec-WebSocket-Key header is repeated."""
        server = ServerProtocol()
        request = make_request()
        request.headers["Sec-WebSocket-Key"] = KEY
        response = server.accept(request)
        server.send_response(response)

        self.assertEqual(response.status_code, 400)
        self.assertHandshakeError(
            server,
            InvalidHeader,
            "invalid Sec-WebSocket-Key header: multiple values",
        )

    def test_invalid_key(self):
        """Handshake fails when the Sec-WebSocket-Key header is invalid."""
        server = ServerProtocol()
        request = make_request()
        del request.headers["Sec-WebSocket-Key"]
        request.headers["Sec-WebSocket-Key"] = "<not Base64 data>"
        response = server.accept(request)
        server.send_response(response)

        self.assertEqual(response.status_code, 400)
        if sys.version_info[:2] >= (3, 11):
            b64_exc = "Only base64 data is allowed"
        else:  # pragma: no cover
            b64_exc = "Non-base64 digit found"
        self.assertHandshakeError(
            server,
            InvalidHeader,
            f"invalid Sec-WebSocket-Key header: <not Base64 data>; {b64_exc}",
        )

    def test_truncated_key(self):
        """Handshake fails when the Sec-WebSocket-Key header is truncated."""
        server = ServerProtocol()
        request = make_request()
        del request.headers["Sec-WebSocket-Key"]
        # 12 bytes instead of 16, Base64-encoded
        request.headers["Sec-WebSocket-Key"] = KEY[:16]
        response = server.accept(request)
        server.send_response(response)

        self.assertEqual(response.status_code, 400)
        self.assertHandshakeError(
            server,
            InvalidHeader,
            f"invalid Sec-WebSocket-Key header: {KEY[:16]}",
        )

    def test_missing_version(self):
        """Handshake fails when the Sec-WebSocket-Version header is missing."""
        server = ServerProtocol()
        request = make_request()
        del request.headers["Sec-WebSocket-Version"]
        response = server.accept(request)
        server.send_response(response)

        self.assertEqual(response.status_code, 400)
        self.assertHandshakeError(
            server,
            InvalidHeader,
            "missing Sec-WebSocket-Version header",
        )

    def test_multiple_version(self):
        """Handshake fails when the Sec-WebSocket-Version header is repeated."""
        server = ServerProtocol()
        request = make_request()
        request.headers["Sec-WebSocket-Version"] = "11"
        response = server.accept(request)
        server.send_response(response)

        self.assertEqual(response.status_code, 400)
        self.assertHandshakeError(
            server,
            InvalidHeader,
            "invalid Sec-WebSocket-Version header: multiple values",
        )

    def test_invalid_version(self):
        """Handshake fails when the Sec-WebSocket-Version header is invalid."""
        server = ServerProtocol()
        request = make_request()
        del request.headers["Sec-WebSocket-Version"]
        request.headers["Sec-WebSocket-Version"] = "11"
        response = server.accept(request)
        server.send_response(response)

        self.assertEqual(response.status_code, 400)
        self.assertHandshakeError(
            server,
            InvalidHeader,
            "invalid Sec-WebSocket-Version header: 11",
        )

    def test_origin(self):
        """Handshake succeeds when checking origin."""
        server = ServerProtocol(origins=["https://example.com"])
        request = make_request()
        request.headers["Origin"] = "https://example.com"
        response = server.accept(request)
        server.send_response(response)

        self.assertHandshakeSuccess(server)
        self.assertEqual(server.origin, "https://example.com")

    def test_no_origin(self):
        """Handshake fails when checking origin and the Origin header is missing."""
        server = ServerProtocol(origins=["https://example.com"])
        request = make_request()
        response = server.accept(request)
        server.send_response(response)

        self.assertEqual(response.status_code, 403)
        self.assertHandshakeError(
            server,
            InvalidOrigin,
            "missing Origin header",
        )

    def test_unexpected_origin(self):
        """Handshake fails when checking origin and the Origin header is unexpected."""
        server = ServerProtocol(origins=["https://example.com"])
        request = make_request()
        request.headers["Origin"] = "https://other.example.com"
        response = server.accept(request)
        server.send_response(response)

        self.assertEqual(response.status_code, 403)
        self.assertHandshakeError(
            server,
            InvalidOrigin,
            "invalid Origin header: https://other.example.com",
        )

    def test_multiple_origin(self):
        """Handshake fails when checking origins and the Origin header is repeated."""
        server = ServerProtocol(
            origins=["https://example.com", "https://other.example.com"]
        )
        request = make_request()
        request.headers["Origin"] = "https://example.com"
        request.headers["Origin"] = "https://other.example.com"
        response = server.accept(request)
        server.send_response(response)

        # This is prohibited by the HTTP specification, so the return code is
        # 400 Bad Request rather than 403 Forbidden.
        self.assertEqual(response.status_code, 400)
        self.assertHandshakeError(
            server,
            InvalidHeader,
            "invalid Origin header: multiple values",
        )

    def test_supported_origin(self):
        """Handshake succeeds when checking origins and the origin is supported."""
        server = ServerProtocol(
            origins=["https://example.com", "https://other.example.com"]
        )
        request = make_request()
        request.headers["Origin"] = "https://other.example.com"
        response = server.accept(request)
        server.send_response(response)

        self.assertHandshakeSuccess(server)
        self.assertEqual(server.origin, "https://other.example.com")

    def test_unsupported_origin(self):
        """Handshake succeeds when checking origins and the origin is unsupported."""
        server = ServerProtocol(
            origins=["https://example.com", "https://other.example.com"]
        )
        request = make_request()
        request.headers["Origin"] = "https://original.example.com"
        response = server.accept(request)
        server.send_response(response)

        self.assertEqual(response.status_code, 403)
        self.assertHandshakeError(
            server,
            InvalidOrigin,
            "invalid Origin header: https://original.example.com",
        )

    def test_no_origin_accepted(self):
        """Handshake succeeds when the lack of an origin is accepted."""
        server = ServerProtocol(origins=[None])
        request = make_request()
        response = server.accept(request)
        server.send_response(response)

        self.assertHandshakeSuccess(server)
        self.assertIsNone(server.origin)

    def test_no_extensions(self):
        """Handshake succeeds without extensions."""
        server = ServerProtocol()
        request = make_request()
        response = server.accept(request)
        server.send_response(response)

        self.assertHandshakeSuccess(server)
        self.assertNotIn("Sec-WebSocket-Extensions", response.headers)
        self.assertEqual(server.extensions, [])

    def test_extension(self):
        """Server enables an extension when the client offers it."""
        server = ServerProtocol(extensions=[ServerOpExtensionFactory()])
        request = make_request()
        request.headers["Sec-WebSocket-Extensions"] = "x-op; op"
        response = server.accept(request)
        server.send_response(response)

        self.assertHandshakeSuccess(server)
        self.assertEqual(response.headers["Sec-WebSocket-Extensions"], "x-op; op")
        self.assertEqual(server.extensions, [OpExtension()])

    def test_extension_not_enabled(self):
        """Server doesn't enable an extension when the client doesn't offer it."""
        server = ServerProtocol(extensions=[ServerOpExtensionFactory()])
        request = make_request()
        response = server.accept(request)
        server.send_response(response)

        self.assertHandshakeSuccess(server)
        self.assertNotIn("Sec-WebSocket-Extensions", response.headers)
        self.assertEqual(server.extensions, [])

    def test_no_extensions_supported(self):
        """Client offers an extension, but the server doesn't support any."""
        server = ServerProtocol()
        request = make_request()
        request.headers["Sec-WebSocket-Extensions"] = "x-op; op"
        response = server.accept(request)
        server.send_response(response)

        self.assertHandshakeSuccess(server)
        self.assertNotIn("Sec-WebSocket-Extensions", response.headers)
        self.assertEqual(server.extensions, [])

    def test_extension_not_supported(self):
        """Client offers an extension, but the server doesn't support it."""
        server = ServerProtocol(extensions=[ServerRsv2ExtensionFactory()])
        request = make_request()
        request.headers["Sec-WebSocket-Extensions"] = "x-op; op"
        response = server.accept(request)
        server.send_response(response)

        self.assertHandshakeSuccess(server)
        self.assertNotIn("Sec-WebSocket-Extensions", response.headers)
        self.assertEqual(server.extensions, [])

    def test_supported_extension_parameters(self):
        """Client offers an extension with parameters supported by the server."""
        server = ServerProtocol(extensions=[ServerOpExtensionFactory("this")])
        request = make_request()
        request.headers["Sec-WebSocket-Extensions"] = "x-op; op=this"
        response = server.accept(request)
        server.send_response(response)

        self.assertHandshakeSuccess(server)
        self.assertEqual(response.headers["Sec-WebSocket-Extensions"], "x-op; op=this")
        self.assertEqual(server.extensions, [OpExtension("this")])

    def test_unsupported_extension_parameters(self):
        """Client offers an extension with parameters unsupported by the server."""
        server = ServerProtocol(extensions=[ServerOpExtensionFactory("this")])
        request = make_request()
        request.headers["Sec-WebSocket-Extensions"] = "x-op; op=that"
        response = server.accept(request)
        server.send_response(response)

        self.assertHandshakeSuccess(server)
        self.assertNotIn("Sec-WebSocket-Extensions", response.headers)
        self.assertEqual(server.extensions, [])

    def test_multiple_supported_extension_parameters(self):
        """Server supports the same extension with several parameters."""
        server = ServerProtocol(
            extensions=[
                ServerOpExtensionFactory("this"),
                ServerOpExtensionFactory("that"),
            ]
        )
        request = make_request()
        request.headers["Sec-WebSocket-Extensions"] = "x-op; op=that"
        response = server.accept(request)
        server.send_response(response)

        self.assertHandshakeSuccess(server)
        self.assertEqual(response.headers["Sec-WebSocket-Extensions"], "x-op; op=that")
        self.assertEqual(server.extensions, [OpExtension("that")])

    def test_multiple_extensions(self):
        """Server enables several extensions when the client offers them."""
        server = ServerProtocol(
            extensions=[ServerOpExtensionFactory(), ServerRsv2ExtensionFactory()]
        )
        request = make_request()
        request.headers["Sec-WebSocket-Extensions"] = "x-op; op"
        request.headers["Sec-WebSocket-Extensions"] = "x-rsv2"
        response = server.accept(request)
        server.send_response(response)

        self.assertHandshakeSuccess(server)
        self.assertEqual(
            response.headers["Sec-WebSocket-Extensions"], "x-op; op, x-rsv2"
        )
        self.assertEqual(server.extensions, [OpExtension(), Rsv2Extension()])

    def test_multiple_extensions_order(self):
        """Server respects the order of extensions set in its configuration."""
        server = ServerProtocol(
            extensions=[ServerOpExtensionFactory(), ServerRsv2ExtensionFactory()]
        )
        request = make_request()
        request.headers["Sec-WebSocket-Extensions"] = "x-rsv2"
        request.headers["Sec-WebSocket-Extensions"] = "x-op; op"
        response = server.accept(request)
        server.send_response(response)

        self.assertHandshakeSuccess(server)
        self.assertEqual(
            response.headers["Sec-WebSocket-Extensions"], "x-rsv2, x-op; op"
        )
        self.assertEqual(server.extensions, [Rsv2Extension(), OpExtension()])

    def test_no_subprotocols(self):
        """Handshake succeeds without subprotocols."""
        server = ServerProtocol()
        request = make_request()
        response = server.accept(request)
        server.send_response(response)

        self.assertHandshakeSuccess(server)
        self.assertNotIn("Sec-WebSocket-Protocol", response.headers)
        self.assertIsNone(server.subprotocol)

    def test_no_subprotocol_requested(self):
        """Server expects a subprotocol, but the client doesn't offer it."""
        server = ServerProtocol(subprotocols=["chat"])
        request = make_request()
        response = server.accept(request)
        server.send_response(response)

        self.assertEqual(response.status_code, 400)
        self.assertHandshakeError(
            server,
            NegotiationError,
            "missing subprotocol",
        )

    def test_subprotocol(self):
        """Server enables a subprotocol when the client offers it."""
        server = ServerProtocol(subprotocols=["chat"])
        request = make_request()
        request.headers["Sec-WebSocket-Protocol"] = "chat"
        response = server.accept(request)
        server.send_response(response)

        self.assertHandshakeSuccess(server)
        self.assertEqual(response.headers["Sec-WebSocket-Protocol"], "chat")
        self.assertEqual(server.subprotocol, "chat")

    def test_no_subprotocols_supported(self):
        """Client offers a subprotocol, but the server doesn't support any."""
        server = ServerProtocol()
        request = make_request()
        request.headers["Sec-WebSocket-Protocol"] = "chat"
        response = server.accept(request)
        server.send_response(response)

        self.assertHandshakeSuccess(server)
        self.assertNotIn("Sec-WebSocket-Protocol", response.headers)
        self.assertIsNone(server.subprotocol)

    def test_multiple_subprotocols(self):
        """Server enables all of the subprotocols when the client offers them."""
        server = ServerProtocol(subprotocols=["superchat", "chat"])
        request = make_request()
        request.headers["Sec-WebSocket-Protocol"] = "chat"
        request.headers["Sec-WebSocket-Protocol"] = "superchat"
        response = server.accept(request)
        server.send_response(response)

        self.assertHandshakeSuccess(server)
        self.assertEqual(response.headers["Sec-WebSocket-Protocol"], "superchat")
        self.assertEqual(server.subprotocol, "superchat")

    def test_supported_subprotocol(self):
        """Server enables one of the subprotocols when the client offers it."""
        server = ServerProtocol(subprotocols=["superchat", "chat"])
        request = make_request()
        request.headers["Sec-WebSocket-Protocol"] = "chat"
        response = server.accept(request)
        server.send_response(response)

        self.assertHandshakeSuccess(server)
        self.assertEqual(response.headers["Sec-WebSocket-Protocol"], "chat")
        self.assertEqual(server.subprotocol, "chat")

    def test_unsupported_subprotocol(self):
        """Server expects one of the subprotocols, but the client doesn't offer any."""
        server = ServerProtocol(subprotocols=["superchat", "chat"])
        request = make_request()
        request.headers["Sec-WebSocket-Protocol"] = "otherchat"
        response = server.accept(request)
        server.send_response(response)

        self.assertEqual(response.status_code, 400)
        self.assertHandshakeError(
            server,
            NegotiationError,
            "invalid subprotocol; expected one of superchat, chat",
        )

    @staticmethod
    def optional_chat(protocol, subprotocols):
        if "chat" in subprotocols:
            return "chat"

    def test_select_subprotocol(self):
        """Server enables a subprotocol with select_subprotocol."""
        server = ServerProtocol(select_subprotocol=self.optional_chat)
        request = make_request()
        request.headers["Sec-WebSocket-Protocol"] = "chat"
        response = server.accept(request)
        server.send_response(response)

        self.assertHandshakeSuccess(server)
        self.assertEqual(response.headers["Sec-WebSocket-Protocol"], "chat")
        self.assertEqual(server.subprotocol, "chat")

    def test_select_no_subprotocol(self):
        """Server doesn't enable any subprotocol with select_subprotocol."""
        server = ServerProtocol(select_subprotocol=self.optional_chat)
        request = make_request()
        request.headers["Sec-WebSocket-Protocol"] = "otherchat"
        response = server.accept(request)
        server.send_response(response)

        self.assertHandshakeSuccess(server)
        self.assertNotIn("Sec-WebSocket-Protocol", response.headers)
        self.assertIsNone(server.subprotocol)


class MiscTests(unittest.TestCase):
    def test_bypass_handshake(self):
        """ServerProtocol bypasses the opening handshake."""
        server = ServerProtocol(state=OPEN)
        server.receive_data(b"\x81\x86\x00\x00\x00\x00Hello!")
        [frame] = server.events_received()
        self.assertEqual(frame, Frame(OP_TEXT, b"Hello!"))

    def test_custom_logger(self):
        """ServerProtocol accepts a logger argument."""
        logger = logging.getLogger("test")
        with self.assertLogs("test", logging.DEBUG) as logs:
            ServerProtocol(logger=logger)
        self.assertEqual(len(logs.records), 1)


class BackwardsCompatibilityTests(DeprecationTestCase):
    def test_server_connection_class(self):
        """ServerConnection is a deprecated alias for ServerProtocol."""
        with self.assertDeprecationWarning(
            "ServerConnection was renamed to ServerProtocol"
        ):
            from websockets.server import ServerConnection

            server = ServerConnection()

        self.assertIsInstance(server, ServerProtocol)
