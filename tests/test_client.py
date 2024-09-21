import contextlib
import dataclasses
import logging
import types
import unittest
from unittest.mock import patch

from websockets.client import *
from websockets.client import backoff
from websockets.datastructures import Headers
from websockets.exceptions import InvalidHandshake, InvalidHeader, InvalidStatus
from websockets.frames import OP_TEXT, Frame
from websockets.http11 import Request, Response
from websockets.protocol import CONNECTING, OPEN
from websockets.uri import parse_uri
from websockets.utils import accept_key

from .extensions.utils import (
    ClientOpExtensionFactory,
    ClientRsv2ExtensionFactory,
    OpExtension,
    Rsv2Extension,
)
from .test_utils import ACCEPT, KEY
from .utils import DATE, DeprecationTestCase


URI = parse_uri("wss://example.com/test")  # for tests where the URI doesn't matter


@patch("websockets.client.generate_key", return_value=KEY)
class BasicTests(unittest.TestCase):
    """Test basic opening handshake scenarios."""

    def test_send_request(self, _generate_key):
        """Client sends a handshake request."""
        client = ClientProtocol(URI)
        request = client.connect()
        client.send_request(request)

        self.assertEqual(
            client.data_to_send(),
            [
                f"GET /test HTTP/1.1\r\n"
                f"Host: example.com\r\n"
                f"Upgrade: websocket\r\n"
                f"Connection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {KEY}\r\n"
                f"Sec-WebSocket-Version: 13\r\n"
                f"\r\n".encode()
            ],
        )
        self.assertFalse(client.close_expected())
        self.assertEqual(client.state, CONNECTING)

    def test_receive_successful_response(self, _generate_key):
        """Client receives a successful handshake response."""
        client = ClientProtocol(URI)
        client.receive_data(
            (
                f"HTTP/1.1 101 Switching Protocols\r\n"
                f"Upgrade: websocket\r\n"
                f"Connection: Upgrade\r\n"
                f"Sec-WebSocket-Accept: {ACCEPT}\r\n"
                f"Date: {DATE}\r\n"
                f"\r\n"
            ).encode(),
        )

        self.assertEqual(client.data_to_send(), [])
        self.assertFalse(client.close_expected())
        self.assertEqual(client.state, OPEN)

    def test_receive_failed_response(self, _generate_key):
        """Client receives a failed handshake response."""
        client = ClientProtocol(URI)
        client.receive_data(
            (
                f"HTTP/1.1 404 Not Found\r\n"
                f"Date: {DATE}\r\n"
                f"Content-Length: 13\r\n"
                f"Content-Type: text/plain; charset=utf-8\r\n"
                f"Connection: close\r\n"
                f"\r\n"
                f"Sorry folks.\n"
            ).encode(),
        )

        self.assertEqual(client.data_to_send(), [b""])
        self.assertTrue(client.close_expected())
        self.assertEqual(client.state, CONNECTING)


class RequestTests(unittest.TestCase):
    """Test generating opening handshake requests."""

    @patch("websockets.client.generate_key", return_value=KEY)
    def test_connect(self, _generate_key):
        """connect() creates an opening handshake request."""
        client = ClientProtocol(URI)
        request = client.connect()

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

    def test_path(self):
        """connect() uses the path from the URI."""
        client = ClientProtocol(parse_uri("wss://example.com/endpoint?test=1"))
        request = client.connect()

        self.assertEqual(request.path, "/endpoint?test=1")

    def test_port(self):
        """connect() uses the port from the URI or the default port."""
        for uri, host in [
            ("ws://example.com/", "example.com"),
            ("ws://example.com:80/", "example.com"),
            ("ws://example.com:8080/", "example.com:8080"),
            ("wss://example.com/", "example.com"),
            ("wss://example.com:443/", "example.com"),
            ("wss://example.com:8443/", "example.com:8443"),
        ]:
            with self.subTest(uri=uri):
                client = ClientProtocol(parse_uri(uri))
                request = client.connect()

                self.assertEqual(request.headers["Host"], host)

    def test_user_info(self):
        """connect() perfoms HTTP Basic Authentication with user info from the URI."""
        client = ClientProtocol(parse_uri("wss://hello:iloveyou@example.com/"))
        request = client.connect()

        self.assertEqual(request.headers["Authorization"], "Basic aGVsbG86aWxvdmV5b3U=")

    def test_origin(self):
        """connect(origin=...) generates an Origin header."""
        client = ClientProtocol(URI, origin="https://example.com")
        request = client.connect()

        self.assertEqual(request.headers["Origin"], "https://example.com")

    def test_extensions(self):
        """connect(extensions=...) generates a Sec-WebSocket-Extensions header."""
        client = ClientProtocol(URI, extensions=[ClientOpExtensionFactory()])
        request = client.connect()

        self.assertEqual(request.headers["Sec-WebSocket-Extensions"], "x-op; op")

    def test_subprotocols(self):
        """connect(subprotocols=...) generates a Sec-WebSocket-Protocol header."""
        client = ClientProtocol(URI, subprotocols=["chat"])
        request = client.connect()

        self.assertEqual(request.headers["Sec-WebSocket-Protocol"], "chat")


@patch("websockets.client.generate_key", return_value=KEY)
class ResponseTests(unittest.TestCase):
    """Test receiving opening handshake responses."""

    def test_receive_successful_response(self, _generate_key):
        """Client receives a successful handshake response."""
        client = ClientProtocol(URI)
        client.receive_data(
            (
                f"HTTP/1.1 101 Switching Protocols\r\n"
                f"Upgrade: websocket\r\n"
                f"Connection: Upgrade\r\n"
                f"Sec-WebSocket-Accept: {ACCEPT}\r\n"
                f"Date: {DATE}\r\n"
                f"\r\n"
            ).encode(),
        )
        [response] = client.events_received()

        self.assertEqual(response.status_code, 101)
        self.assertEqual(response.reason_phrase, "Switching Protocols")
        self.assertEqual(
            response.headers,
            Headers(
                {
                    "Upgrade": "websocket",
                    "Connection": "Upgrade",
                    "Sec-WebSocket-Accept": ACCEPT,
                    "Date": DATE,
                }
            ),
        )
        self.assertIsNone(response.body)
        self.assertIsNone(client.handshake_exc)

    def test_receive_failed_response(self, _generate_key):
        """Client receives a failed handshake response."""
        client = ClientProtocol(URI)
        client.receive_data(
            (
                f"HTTP/1.1 404 Not Found\r\n"
                f"Date: {DATE}\r\n"
                f"Content-Length: 13\r\n"
                f"Content-Type: text/plain; charset=utf-8\r\n"
                f"Connection: close\r\n"
                f"\r\n"
                f"Sorry folks.\n"
            ).encode(),
        )
        [response] = client.events_received()

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.reason_phrase, "Not Found")
        self.assertEqual(
            response.headers,
            Headers(
                {
                    "Date": DATE,
                    "Content-Length": "13",
                    "Content-Type": "text/plain; charset=utf-8",
                    "Connection": "close",
                }
            ),
        )
        self.assertEqual(response.body, b"Sorry folks.\n")
        self.assertIsInstance(client.handshake_exc, InvalidStatus)
        self.assertEqual(
            str(client.handshake_exc),
            "server rejected WebSocket connection: HTTP 404",
        )

    def test_receive_no_response(self, _generate_key):
        """Client receives no handshake response."""
        client = ClientProtocol(URI)
        client.receive_eof()

        self.assertEqual(client.events_received(), [])
        self.assertIsInstance(client.handshake_exc, EOFError)
        self.assertEqual(
            str(client.handshake_exc),
            "connection closed while reading HTTP status line",
        )

    def test_receive_truncated_response(self, _generate_key):
        """Client receives a truncated handshake response."""
        client = ClientProtocol(URI)
        client.receive_data(b"HTTP/1.1 101 Switching Protocols\r\n")
        client.receive_eof()

        self.assertEqual(client.events_received(), [])
        self.assertIsInstance(client.handshake_exc, EOFError)
        self.assertEqual(
            str(client.handshake_exc),
            "connection closed while reading HTTP headers",
        )

    def test_receive_random_response(self, _generate_key):
        """Client receives a junk handshake response."""
        client = ClientProtocol(URI)
        client.receive_data(b"220 smtp.invalid\r\n")
        client.receive_data(b"250 Hello relay.invalid\r\n")
        client.receive_data(b"250 Ok\r\n")
        client.receive_data(b"250 Ok\r\n")

        self.assertEqual(client.events_received(), [])
        self.assertIsInstance(client.handshake_exc, ValueError)
        self.assertEqual(
            str(client.handshake_exc),
            "invalid HTTP status line: 220 smtp.invalid",
        )


@contextlib.contextmanager
def alter_and_receive_response(client):
    """Generate a handshake response that can be altered for testing."""
    # We could start by sending a handshake request, i.e.:
    # request = client.connect()
    # client.send_request(request)
    # However, in the current implementation, these calls have no effect on the
    # state of the client. Therefore, they're unnecessary and can be skipped.
    response = Response(
        status_code=101,
        reason_phrase="Switching Protocols",
        headers=Headers(
            {
                "Upgrade": "websocket",
                "Connection": "Upgrade",
                "Sec-WebSocket-Accept": accept_key(client.key),
            }
        ),
    )
    yield response
    client.receive_data(response.serialize())
    [parsed_response] = client.events_received()
    assert response == dataclasses.replace(parsed_response, _exception=None)


class HandshakeTests(unittest.TestCase):
    """Test processing of handshake responses to configure the connection."""

    def assertHandshakeSuccess(self, client):
        """Assert that the opening handshake succeeded."""
        self.assertEqual(client.state, OPEN)
        self.assertIsNone(client.handshake_exc)

    def assertHandshakeError(self, client, exc_type, msg):
        """Assert that the opening handshake failed with the given exception."""
        self.assertEqual(client.state, CONNECTING)
        self.assertIsInstance(client.handshake_exc, exc_type)
        # Exception chaining isn't used is client handshake implementation.
        assert client.handshake_exc.__cause__ is None
        self.assertEqual(str(client.handshake_exc), msg)

    def test_basic(self):
        """Handshake succeeds."""
        client = ClientProtocol(URI)
        with alter_and_receive_response(client):
            pass

        self.assertHandshakeSuccess(client)

    def test_missing_connection(self):
        """Handshake fails when the Connection header is missing."""
        client = ClientProtocol(URI)
        with alter_and_receive_response(client) as response:
            del response.headers["Connection"]

        self.assertHandshakeError(
            client,
            InvalidHeader,
            "missing Connection header",
        )

    def test_invalid_connection(self):
        """Handshake fails when the Connection header is invalid."""
        client = ClientProtocol(URI)
        with alter_and_receive_response(client) as response:
            del response.headers["Connection"]
            response.headers["Connection"] = "close"

        self.assertHandshakeError(
            client,
            InvalidHeader,
            "invalid Connection header: close",
        )

    def test_missing_upgrade(self):
        """Handshake fails when the Upgrade header is missing."""
        client = ClientProtocol(URI)
        with alter_and_receive_response(client) as response:
            del response.headers["Upgrade"]

        self.assertHandshakeError(
            client,
            InvalidHeader,
            "missing Upgrade header",
        )

    def test_invalid_upgrade(self):
        """Handshake fails when the Upgrade header is invalid."""
        client = ClientProtocol(URI)
        with alter_and_receive_response(client) as response:
            del response.headers["Upgrade"]
            response.headers["Upgrade"] = "h2c"

        self.assertHandshakeError(
            client,
            InvalidHeader,
            "invalid Upgrade header: h2c",
        )

    def test_missing_accept(self):
        """Handshake fails when the Sec-WebSocket-Accept header is missing."""
        client = ClientProtocol(URI)
        with alter_and_receive_response(client) as response:
            del response.headers["Sec-WebSocket-Accept"]

        self.assertHandshakeError(
            client,
            InvalidHeader,
            "missing Sec-WebSocket-Accept header",
        )

    def test_multiple_accept(self):
        """Handshake fails when the Sec-WebSocket-Accept header is repeated."""
        client = ClientProtocol(URI)
        with alter_and_receive_response(client) as response:
            response.headers["Sec-WebSocket-Accept"] = ACCEPT

        self.assertHandshakeError(
            client,
            InvalidHeader,
            "invalid Sec-WebSocket-Accept header: multiple values",
        )

    def test_invalid_accept(self):
        """Handshake fails when the Sec-WebSocket-Accept header is invalid."""
        client = ClientProtocol(URI)
        with alter_and_receive_response(client) as response:
            del response.headers["Sec-WebSocket-Accept"]
            response.headers["Sec-WebSocket-Accept"] = ACCEPT

        self.assertHandshakeError(
            client,
            InvalidHeader,
            f"invalid Sec-WebSocket-Accept header: {ACCEPT}",
        )

    def test_no_extensions(self):
        """Handshake succeeds without extensions."""
        client = ClientProtocol(URI)
        with alter_and_receive_response(client):
            pass

        self.assertHandshakeSuccess(client)
        self.assertEqual(client.extensions, [])

    def test_offer_extension(self):
        """Client offers an extension."""
        client = ClientProtocol(URI, extensions=[ClientRsv2ExtensionFactory()])
        request = client.connect()

        self.assertEqual(request.headers["Sec-WebSocket-Extensions"], "x-rsv2")

    def test_enable_extension(self):
        """Client offers an extension and the server enables it."""
        client = ClientProtocol(URI, extensions=[ClientRsv2ExtensionFactory()])
        with alter_and_receive_response(client) as response:
            response.headers["Sec-WebSocket-Extensions"] = "x-rsv2"

        self.assertHandshakeSuccess(client)
        self.assertEqual(client.extensions, [Rsv2Extension()])

    def test_extension_not_enabled(self):
        """Client offers an extension, but the server doesn't enable it."""
        client = ClientProtocol(URI, extensions=[ClientRsv2ExtensionFactory()])
        with alter_and_receive_response(client):
            pass

        self.assertHandshakeSuccess(client)
        self.assertEqual(client.extensions, [])

    def test_no_extensions_offered(self):
        """Server enables an extension when the client didn't offer any."""
        client = ClientProtocol(URI)
        with alter_and_receive_response(client) as response:
            response.headers["Sec-WebSocket-Extensions"] = "x-rsv2"

        self.assertHandshakeError(
            client,
            InvalidHandshake,
            "no extensions supported",
        )

    def test_extension_not_offered(self):
        """Server enables an extension that the client didn't offer."""
        client = ClientProtocol(URI, extensions=[ClientRsv2ExtensionFactory()])
        with alter_and_receive_response(client) as response:
            response.headers["Sec-WebSocket-Extensions"] = "x-op; op"

        self.assertHandshakeError(
            client,
            InvalidHandshake,
            "Unsupported extension: name = x-op, params = [('op', None)]",
        )

    def test_supported_extension_parameters(self):
        """Server enables an extension with parameters supported by the client."""
        client = ClientProtocol(URI, extensions=[ClientOpExtensionFactory("this")])
        with alter_and_receive_response(client) as response:
            response.headers["Sec-WebSocket-Extensions"] = "x-op; op=this"

        self.assertHandshakeSuccess(client)
        self.assertEqual(client.extensions, [OpExtension("this")])

    def test_unsupported_extension_parameters(self):
        """Server enables an extension with parameters unsupported by the client."""
        client = ClientProtocol(URI, extensions=[ClientOpExtensionFactory("this")])
        with alter_and_receive_response(client) as response:
            response.headers["Sec-WebSocket-Extensions"] = "x-op; op=that"

        self.assertHandshakeError(
            client,
            InvalidHandshake,
            "Unsupported extension: name = x-op, params = [('op', 'that')]",
        )

    def test_multiple_supported_extension_parameters(self):
        """Client offers the same extension with several parameters."""
        client = ClientProtocol(
            URI,
            extensions=[
                ClientOpExtensionFactory("this"),
                ClientOpExtensionFactory("that"),
            ],
        )
        with alter_and_receive_response(client) as response:
            response.headers["Sec-WebSocket-Extensions"] = "x-op; op=that"

        self.assertHandshakeSuccess(client)
        self.assertEqual(client.extensions, [OpExtension("that")])

    def test_multiple_extensions(self):
        """Client offers several extensions and the server enables them."""
        client = ClientProtocol(
            URI,
            extensions=[
                ClientOpExtensionFactory(),
                ClientRsv2ExtensionFactory(),
            ],
        )
        with alter_and_receive_response(client) as response:
            response.headers["Sec-WebSocket-Extensions"] = "x-op; op"
            response.headers["Sec-WebSocket-Extensions"] = "x-rsv2"

        self.assertHandshakeSuccess(client)
        self.assertEqual(client.extensions, [OpExtension(), Rsv2Extension()])

    def test_multiple_extensions_order(self):
        """Client respects the order of extensions chosen by the server."""
        client = ClientProtocol(
            URI,
            extensions=[
                ClientOpExtensionFactory(),
                ClientRsv2ExtensionFactory(),
            ],
        )
        with alter_and_receive_response(client) as response:
            response.headers["Sec-WebSocket-Extensions"] = "x-rsv2"
            response.headers["Sec-WebSocket-Extensions"] = "x-op; op"

        self.assertHandshakeSuccess(client)
        self.assertEqual(client.extensions, [Rsv2Extension(), OpExtension()])

    def test_no_subprotocols(self):
        """Handshake succeeds without subprotocols."""
        client = ClientProtocol(URI)
        with alter_and_receive_response(client):
            pass

        self.assertHandshakeSuccess(client)
        self.assertIsNone(client.subprotocol)

    def test_no_subprotocol_requested(self):
        """Client doesn't offer a subprotocol, but the server enables one."""
        client = ClientProtocol(URI)
        with alter_and_receive_response(client) as response:
            response.headers["Sec-WebSocket-Protocol"] = "chat"

        self.assertHandshakeError(
            client,
            InvalidHandshake,
            "no subprotocols supported",
        )

    def test_offer_subprotocol(self):
        """Client offers a subprotocol."""
        client = ClientProtocol(URI, subprotocols=["chat"])
        request = client.connect()

        self.assertEqual(request.headers["Sec-WebSocket-Protocol"], "chat")

    def test_enable_subprotocol(self):
        """Client offers a subprotocol and the server enables it."""
        client = ClientProtocol(URI, subprotocols=["chat"])
        with alter_and_receive_response(client) as response:
            response.headers["Sec-WebSocket-Protocol"] = "chat"

        self.assertHandshakeSuccess(client)
        self.assertEqual(client.subprotocol, "chat")

    def test_no_subprotocol_accepted(self):
        """Client offers a subprotocol, but the server doesn't enable it."""
        client = ClientProtocol(URI, subprotocols=["chat"])
        with alter_and_receive_response(client):
            pass

        self.assertHandshakeSuccess(client)
        self.assertIsNone(client.subprotocol)

    def test_multiple_subprotocols(self):
        """Client offers several subprotocols and the server enables one."""
        client = ClientProtocol(URI, subprotocols=["superchat", "chat"])
        with alter_and_receive_response(client) as response:
            response.headers["Sec-WebSocket-Protocol"] = "chat"

        self.assertHandshakeSuccess(client)
        self.assertEqual(client.subprotocol, "chat")

    def test_unsupported_subprotocol(self):
        """Client offers subprotocols but the server enables another one."""
        client = ClientProtocol(URI, subprotocols=["superchat", "chat"])
        with alter_and_receive_response(client) as response:
            response.headers["Sec-WebSocket-Protocol"] = "otherchat"

        self.assertHandshakeError(
            client,
            InvalidHandshake,
            "unsupported subprotocol: otherchat",
        )

    def test_multiple_subprotocols_accepted(self):
        """Server attempts to enable multiple subprotocols."""
        client = ClientProtocol(URI, subprotocols=["superchat", "chat"])
        with alter_and_receive_response(client) as response:
            response.headers["Sec-WebSocket-Protocol"] = "superchat"
            response.headers["Sec-WebSocket-Protocol"] = "chat"

        self.assertHandshakeError(
            client,
            InvalidHandshake,
            "invalid Sec-WebSocket-Protocol header: "
            "multiple values: superchat, chat",
        )


class MiscTests(unittest.TestCase):
    def test_bypass_handshake(self):
        """ClientProtocol bypasses the opening handshake."""
        client = ClientProtocol(URI, state=OPEN)
        client.receive_data(b"\x81\x06Hello!")
        [frame] = client.events_received()
        self.assertEqual(frame, Frame(OP_TEXT, b"Hello!"))

    def test_custom_logger(self):
        """ClientProtocol accepts a logger argument."""
        logger = logging.getLogger("test")
        with self.assertLogs("test", logging.DEBUG) as logs:
            ClientProtocol(URI, logger=logger)
        self.assertEqual(len(logs.records), 1)


class BackwardsCompatibilityTests(DeprecationTestCase):
    def test_client_connection_class(self):
        """ClientConnection is a deprecated alias for ClientProtocol."""
        with self.assertDeprecationWarning(
            "ClientConnection was renamed to ClientProtocol"
        ):
            from websockets.client import ClientConnection

            client = ClientConnection("ws://localhost/")

        self.assertIsInstance(client, ClientProtocol)


class BackoffTests(unittest.TestCase):
    def test_backoff(self):
        """backoff() yields a random delay, then exponentially increasing delays."""
        backoff_gen = backoff()
        self.assertIsInstance(backoff_gen, types.GeneratorType)

        initial_delay = next(backoff_gen)
        self.assertGreaterEqual(initial_delay, 0)
        self.assertLess(initial_delay, 5)

        following_delays = [int(next(backoff_gen)) for _ in range(9)]
        self.assertEqual(following_delays, [3, 5, 8, 13, 21, 34, 55, 89, 90])
