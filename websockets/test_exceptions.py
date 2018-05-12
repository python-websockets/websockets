import unittest

from .exceptions import *


class ExceptionsTests(unittest.TestCase):

    def test_str(self):
        for exception, exception_str in [
            (
                InvalidHandshake("Invalid request"),
                "Invalid request",
            ),
            (
                AbortHandshake(200, [], b'OK\n'),
                "HTTP 200, 0 headers, 3 bytes",
            ),
            (
                InvalidMessage("Malformed HTTP message"),
                "Malformed HTTP message",
            ),
            (
                InvalidHeader('Name', ''),
                "Missing or empty Name header",
            ),
            (
                InvalidHeader('Name', 'Value'),
                "Invalid Name header: Value",
            ),
            (
                InvalidHeaderFormat(
                    'Sec-WebSocket-Protocol', "expected token", 'a=|', 3),
                "Invalid Sec-WebSocket-Protocol header: "
                "expected token at 3 in a=|",
            ),
            (
                InvalidHeaderValue('Sec-WebSocket-Version', '42'),
                "Invalid Sec-WebSocket-Version header: 42",
            ),

            (
                InvalidUpgrade('Upgrade', ''),
                "Missing or empty Upgrade header",
            ),
            (
                InvalidUpgrade('Connection', 'websocket'),
                "Invalid Connection header: websocket",
            ),
            (
                InvalidOrigin('http://bad.origin'),
                'Invalid Origin header: http://bad.origin',
            ),
            (
                InvalidStatusCode(403),
                "Status code not 101: 403",
            ),
            (
                NegotiationError("Unsupported subprotocol: spam"),
                "Unsupported subprotocol: spam",
            ),
            (
                InvalidParameterName('|'),
                "Invalid parameter name: |",
            ),
            (
                InvalidParameterValue('a', '|'),
                "Invalid value for parameter a: |",
            ),
            (
                DuplicateParameter('a'),
                "Duplicate parameter: a",
            ),
            (
                InvalidState("WebSocket connection isn't established yet"),
                "WebSocket connection isn't established yet",
            ),
            (
                ConnectionClosed(1000, ''),
                "WebSocket connection is closed: code = 1000 "
                "(OK), no reason",
            ),
            (
                ConnectionClosed(1001, 'bye'),
                "WebSocket connection is closed: code = 1001 "
                "(going away), reason = bye",
            ),
            (
                ConnectionClosed(1006, None),
                "WebSocket connection is closed: code = 1006 "
                "(connection closed abnormally [internal]), no reason"
            ),
            (
                ConnectionClosed(1016, None),
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
                InvalidURI("| isn't a valid URI"),
                "| isn't a valid URI",
            ),
            (
                PayloadTooBig("Payload length exceeds limit: 2 > 1 bytes"),
                "Payload length exceeds limit: 2 > 1 bytes",
            ),
            (
                WebSocketProtocolError("Invalid opcode: 7"),
                "Invalid opcode: 7",
            ),
        ]:
            with self.subTest(exception=exception):
                self.assertEqual(str(exception), exception_str)
