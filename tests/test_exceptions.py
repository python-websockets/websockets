import unittest

from websockets.datastructures import Headers
from websockets.exceptions import *
from websockets.frames import Close, CloseCode
from websockets.http11 import Response

from .utils import DeprecationTestCase


class ExceptionsTests(unittest.TestCase):
    def test_str(self):
        for exception, exception_str in [
            (
                WebSocketException("something went wrong"),
                "something went wrong",
            ),
            (
                ConnectionClosed(
                    Close(CloseCode.NORMAL_CLOSURE, ""),
                    Close(CloseCode.NORMAL_CLOSURE, ""),
                    True,
                ),
                "received 1000 (OK); then sent 1000 (OK)",
            ),
            (
                ConnectionClosed(
                    Close(CloseCode.GOING_AWAY, "Bye!"),
                    Close(CloseCode.GOING_AWAY, "Bye!"),
                    False,
                ),
                "sent 1001 (going away) Bye!; then received 1001 (going away) Bye!",
            ),
            (
                ConnectionClosed(
                    Close(CloseCode.NORMAL_CLOSURE, "race"),
                    Close(CloseCode.NORMAL_CLOSURE, "cond"),
                    True,
                ),
                "received 1000 (OK) race; then sent 1000 (OK) cond",
            ),
            (
                ConnectionClosed(
                    Close(CloseCode.NORMAL_CLOSURE, "cond"),
                    Close(CloseCode.NORMAL_CLOSURE, "race"),
                    False,
                ),
                "sent 1000 (OK) race; then received 1000 (OK) cond",
            ),
            (
                ConnectionClosed(
                    None,
                    Close(CloseCode.MESSAGE_TOO_BIG, ""),
                    None,
                ),
                "sent 1009 (message too big); no close frame received",
            ),
            (
                ConnectionClosed(
                    Close(CloseCode.PROTOCOL_ERROR, ""),
                    None,
                    None,
                ),
                "received 1002 (protocol error); no close frame sent",
            ),
            (
                ConnectionClosedOK(
                    Close(CloseCode.NORMAL_CLOSURE, ""),
                    Close(CloseCode.NORMAL_CLOSURE, ""),
                    True,
                ),
                "received 1000 (OK); then sent 1000 (OK)",
            ),
            (
                ConnectionClosedError(
                    None,
                    None,
                    None,
                ),
                "no close frame received or sent",
            ),
            (
                InvalidURI("|", "not at all!"),
                "| isn't a valid URI: not at all!",
            ),
            (
                InvalidHandshake("invalid request"),
                "invalid request",
            ),
            (
                SecurityError("redirect from WSS to WS"),
                "redirect from WSS to WS",
            ),
            (
                InvalidStatus(Response(401, "Unauthorized", Headers())),
                "server rejected WebSocket connection: HTTP 401",
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
                InvalidHeaderFormat("Sec-WebSocket-Protocol", "exp. token", "a=|", 3),
                "invalid Sec-WebSocket-Protocol header: exp. token at 3 in a=|",
            ),
            (
                InvalidHeaderValue("Sec-WebSocket-Version", "42"),
                "invalid Sec-WebSocket-Version header: 42",
            ),
            (
                InvalidOrigin("http://bad.origin"),
                "invalid Origin header: http://bad.origin",
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
                NegotiationError("unsupported subprotocol: spam"),
                "unsupported subprotocol: spam",
            ),
            (
                DuplicateParameter("a"),
                "duplicate parameter: a",
            ),
            (
                InvalidParameterName("|"),
                "invalid parameter name: |",
            ),
            (
                InvalidParameterValue("a", None),
                "missing value for parameter a",
            ),
            (
                InvalidParameterValue("a", ""),
                "empty value for parameter a",
            ),
            (
                InvalidParameterValue("a", "|"),
                "invalid value for parameter a: |",
            ),
            (
                ProtocolError("invalid opcode: 7"),
                "invalid opcode: 7",
            ),
            (
                PayloadTooBig(None, 4),
                "frame exceeds limit of 4 bytes",
            ),
            (
                PayloadTooBig(8, 4),
                "frame with 8 bytes exceeds limit of 4 bytes",
            ),
            (
                PayloadTooBig(8, 4, 12),
                "frame with 8 bytes after reading 12 bytes exceeds limit of 16 bytes",
            ),
            (
                InvalidState("WebSocket connection isn't established yet"),
                "WebSocket connection isn't established yet",
            ),
            (
                ConcurrencyError("get() or get_iter() is already running"),
                "get() or get_iter() is already running",
            ),
        ]:
            with self.subTest(exception=exception):
                self.assertEqual(str(exception), exception_str)


class DeprecationTests(DeprecationTestCase):
    def test_connection_closed_attributes_deprecation(self):
        exception = ConnectionClosed(Close(CloseCode.NORMAL_CLOSURE, "OK"), None, None)
        with self.assertDeprecationWarning(
            "ConnectionClosed.code is deprecated; "
            "use Protocol.close_code or ConnectionClosed.rcvd.code"
        ):
            self.assertEqual(exception.code, CloseCode.NORMAL_CLOSURE)
        with self.assertDeprecationWarning(
            "ConnectionClosed.reason is deprecated; "
            "use Protocol.close_reason or ConnectionClosed.rcvd.reason"
        ):
            self.assertEqual(exception.reason, "OK")

    def test_connection_closed_attributes_deprecation_defaults(self):
        exception = ConnectionClosed(None, None, None)
        with self.assertDeprecationWarning(
            "ConnectionClosed.code is deprecated; "
            "use Protocol.close_code or ConnectionClosed.rcvd.code"
        ):
            self.assertEqual(exception.code, CloseCode.ABNORMAL_CLOSURE)
        with self.assertDeprecationWarning(
            "ConnectionClosed.reason is deprecated; "
            "use Protocol.close_reason or ConnectionClosed.rcvd.reason"
        ):
            self.assertEqual(exception.reason, "")

    def test_payload_too_big_with_message(self):
        with self.assertDeprecationWarning(
            "PayloadTooBig(message) is deprecated; "
            "change to PayloadTooBig(size, max_size)",
        ):
            exc = PayloadTooBig("payload length exceeds limit: 2 > 1 bytes")
        self.assertEqual(str(exc), "payload length exceeds limit: 2 > 1 bytes")
