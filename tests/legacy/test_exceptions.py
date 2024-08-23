import unittest

from websockets.datastructures import Headers
from websockets.legacy.exceptions import *


class ExceptionsTests(unittest.TestCase):
    def test_str(self):
        for exception, exception_str in [
            (
                InvalidMessage("malformed HTTP message"),
                "malformed HTTP message",
            ),
            (
                InvalidStatusCode(403, Headers()),
                "server rejected WebSocket connection: HTTP 403",
            ),
            (
                AbortHandshake(200, Headers(), b"OK\n"),
                "HTTP 200, 0 headers, 3 bytes",
            ),
        ]:
            with self.subTest(exception=exception):
                self.assertEqual(str(exception), exception_str)
