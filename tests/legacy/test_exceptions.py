import unittest

from websockets.legacy.exceptions import *


class ExceptionsTests(unittest.TestCase):
    def test_str(self):
        for exception, exception_str in [
            (
                InvalidMessage("malformed HTTP message"),
                "malformed HTTP message",
            ),
        ]:
            with self.subTest(exception=exception):
                self.assertEqual(str(exception), exception_str)
