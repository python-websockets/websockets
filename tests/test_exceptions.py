import unittest

from websockets.exceptions import *
from websockets.http import Headers


class ExceptionsTests(unittest.TestCase):
    def test_str(self):
        for exception, exception_str in [
            # fmt: off
            (
                InvalidHandshake("invalid request"),
                "invalid request",
            ),
            (
                AbortHandshake(200, Headers(), b"OK\n"),
                "HTTP 200, 0 headers, 3 bytes",
            ),
            (
                RedirectHandshake("wss://example.com"),
                "redirect to wss://example.com",
            ),
            (
                InvalidMessage("malformed HTTP message"),
                "malformed HTTP message",
            ),
            (
                InvalidHeader("Name"),
                "missing Name header",
            ),
            (
                InvalidHeader("Name", None),
                "missing Name header",
            ),
            (
                InvalidHeader("Name", ""),
                "empty Name header",
            ),
            (
                InvalidHeader("Name", "Value"),
                "invalid Name header: Value",
            ),
            (
                InvalidHeaderFormat(
                    "Sec-WebSocket-Protocol", "expected token", "a=|", 3
                ),
                "invalid Sec-WebSocket-Protocol header: "
                "expected token at 3 in a=|",
            ),
            (
                InvalidHeaderValue("Sec-WebSocket-Version", "42"),
                "invalid Sec-WebSocket-Version header: 42",
            ),
            (
                InvalidUpgrade("Upgrade"),
                "missing Upgrade header",
            ),
            (
                InvalidUpgrade("Connection", "websocket"),
                "invalid Connection header: websocket",
            ),
            (
                InvalidOrigin("http://bad.origin"),
                "invalid Origin header: http://bad.origin",
            ),
            (
                InvalidStatusCode(403),
                "server rejected WebSocket connection: HTTP 403",
            ),
            (
                NegotiationError("unsupported subprotocol: spam"),
                "unsupported subprotocol: spam",
            ),
            (
                InvalidParameterName("|"),
                "invalid parameter name: |",
            ),
            (
                InvalidParameterValue("a", "|"),
                "invalid value for parameter a: |",
            ),
            (
                DuplicateParameter("a"),
                "duplicate parameter: a",
            ),
            (
                InvalidState("WebSocket connection isn't established yet"),
                "WebSocket connection isn't established yet",
            ),
            (
                ConnectionClosed(1000, ""),
                "WebSocket connection is closed: code = 1000 "
                "(OK), no reason",
            ),
            (
                ConnectionClosedOK(1001, "bye"),
                "WebSocket connection is closed: code = 1001 "
                "(going away), reason = bye",
            ),
            (
                ConnectionClosed(1006, None),
                "WebSocket connection is closed: code = 1006 "
                "(connection closed abnormally [internal]), no reason"
            ),
            (
                ConnectionClosedError(1016, None),
                "WebSocket connection is closed: code = 1016 "
                "(unknown), no reason"
            ),
            (
                ConnectionClosed(3000, None),
                "WebSocket connection is closed: code = 3000 "
                "(registered), no reason"
            ),
            (
                ConnectionClosed(4000, None),
                "WebSocket connection is closed: code = 4000 "
                "(private use), no reason"
            ),
            (
                InvalidURI("|"),
                "| isn't a valid URI",
            ),
            (
                PayloadTooBig("payload length exceeds limit: 2 > 1 bytes"),
                "payload length exceeds limit: 2 > 1 bytes",
            ),
            (
                WebSocketProtocolError("invalid opcode: 7"),
                "invalid opcode: 7",
            ),
            # fmt: on
        ]:
            with self.subTest(exception=exception):
                self.assertEqual(str(exception), exception_str)
