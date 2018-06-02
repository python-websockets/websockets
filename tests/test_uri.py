import unittest

from websockets.exceptions import InvalidURI
from websockets.uri import *


VALID_URIS = [
    ("ws://localhost/", (False, "localhost", 80, "/", None)),
    ("wss://localhost/", (True, "localhost", 443, "/", None)),
    ("ws://localhost/path?query", (False, "localhost", 80, "/path?query", None)),
    ("WS://LOCALHOST/PATH?QUERY", (False, "localhost", 80, "/PATH?QUERY", None)),
    ("ws://user:pass@localhost/", (False, "localhost", 80, "/", ("user", "pass"))),
]

INVALID_URIS = [
    "http://localhost/",
    "https://localhost/",
    "ws://localhost/path#fragment",
    "ws://user@localhost/",
]

VALID_PROXY_URIS = [
    ("http://localhost", (False, "localhost", 80, None)),
    ("http://localhost/", (False, "localhost", 80, None)),
    ("https://localhost", (True, "localhost", 443, None)),
    ("http://user:pass@localhost", (False, "localhost", 80, ("user", "pass"))),
]

INVALID_PROXY_URIS = [
    "http://localhost/path",
    "ws://localhost/",
    "wss://localhost/",
]

class URITests(unittest.TestCase):
    def test_parse_uri_success(self):
        for uri, parsed in VALID_URIS:
            with self.subTest(uri=uri):
                self.assertEqual(parse_uri(uri), parsed)

    def test_parse_uri_error(self):
        for uri in INVALID_URIS:
            with self.subTest(uri=uri):
                with self.assertRaises(InvalidURI):
                    parse_uri(uri)

    def test_parse_proxy_uri_success(self):
        for uri, parsed in VALID_PROXY_URIS:
            with self.subTest(uri=uri):
                self.assertEqual(parse_proxy_uri(uri), parsed)

    def test_parse_proxy_uri_error(self):
        for uri in INVALID_PROXY_URIS:
            with self.subTest(uri=uri):
                with self.assertRaises(InvalidURI):
                    parse_proxy_uri(uri)
