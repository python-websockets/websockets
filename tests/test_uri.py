import os
import unittest
from unittest.mock import patch

from websockets.exceptions import InvalidProxy, InvalidURI
from websockets.uri import *
from websockets.uri import Proxy, get_proxy, parse_proxy


VALID_URIS = [
    (
        "ws://localhost/",
        WebSocketURI(False, "localhost", 80, "/", "", None, None),
    ),
    (
        "wss://localhost/",
        WebSocketURI(True, "localhost", 443, "/", "", None, None),
    ),
    (
        "ws://localhost",
        WebSocketURI(False, "localhost", 80, "", "", None, None),
    ),
    (
        "ws://localhost/path?query",
        WebSocketURI(False, "localhost", 80, "/path", "query", None, None),
    ),
    (
        "ws://localhost/path;params",
        WebSocketURI(False, "localhost", 80, "/path;params", "", None, None),
    ),
    (
        "WS://LOCALHOST/PATH?QUERY",
        WebSocketURI(False, "localhost", 80, "/PATH", "QUERY", None, None),
    ),
    (
        "ws://user:pass@localhost/",
        WebSocketURI(False, "localhost", 80, "/", "", "user", "pass"),
    ),
    (
        "ws://høst/",
        WebSocketURI(False, "xn--hst-0na", 80, "/", "", None, None),
    ),
    (
        "ws://üser:påss@høst/πass?qùéry",
        WebSocketURI(
            False,
            "xn--hst-0na",
            80,
            "/%CF%80ass",
            "q%C3%B9%C3%A9ry",
            "%C3%BCser",
            "p%C3%A5ss",
        ),
    ),
]

INVALID_URIS = [
    "http://localhost/",
    "https://localhost/",
    "ws://localhost/path#fragment",
    "ws://user@localhost/",
    "ws:///path",
]

URIS_WITH_RESOURCE_NAMES = [
    ("ws://localhost/", "/"),
    ("ws://localhost", "/"),
    ("ws://localhost/path?query", "/path?query"),
    ("ws://høst/πass?qùéry", "/%CF%80ass?q%C3%B9%C3%A9ry"),
]

URIS_WITH_USER_INFO = [
    ("ws://localhost/", None),
    ("ws://user:pass@localhost/", ("user", "pass")),
    ("ws://üser:påss@høst/", ("%C3%BCser", "p%C3%A5ss")),
]

VALID_PROXIES = [
    (
        "http://proxy:8080",
        Proxy("http", "proxy", 8080, None, None),
    ),
    (
        "https://proxy:8080",
        Proxy("https", "proxy", 8080, None, None),
    ),
    (
        "http://proxy",
        Proxy("http", "proxy", 80, None, None),
    ),
    (
        "http://proxy:8080/",
        Proxy("http", "proxy", 8080, None, None),
    ),
    (
        "http://PROXY:8080",
        Proxy("http", "proxy", 8080, None, None),
    ),
    (
        "http://user:pass@proxy:8080",
        Proxy("http", "proxy", 8080, "user", "pass"),
    ),
    (
        "http://høst:8080/",
        Proxy("http", "xn--hst-0na", 8080, None, None),
    ),
    (
        "http://üser:påss@høst:8080",
        Proxy("http", "xn--hst-0na", 8080, "%C3%BCser", "p%C3%A5ss"),
    ),
]

INVALID_PROXIES = [
    "ws://proxy:8080",
    "wss://proxy:8080",
    "http://proxy:8080/path",
    "http://proxy:8080/?query",
    "http://proxy:8080/#fragment",
    "http://user@proxy",
    "http:///",
]

PROXIES_WITH_USER_INFO = [
    ("http://proxy", None),
    ("http://user:pass@proxy", ("user", "pass")),
    ("http://üser:påss@høst", ("%C3%BCser", "p%C3%A5ss")),
]

PROXY_ENVS = [
    (
        {"ws_proxy": "http://proxy:8080"},
        "ws://example.com/",
        "http://proxy:8080",
    ),
    (
        {"ws_proxy": "http://proxy:8080"},
        "wss://example.com/",
        None,
    ),
    (
        {"wss_proxy": "http://proxy:8080"},
        "ws://example.com/",
        None,
    ),
    (
        {"wss_proxy": "http://proxy:8080"},
        "wss://example.com/",
        "http://proxy:8080",
    ),
    (
        {"http_proxy": "http://proxy:8080"},
        "ws://example.com/",
        "http://proxy:8080",
    ),
    (
        {"http_proxy": "http://proxy:8080"},
        "wss://example.com/",
        None,
    ),
    (
        {"https_proxy": "http://proxy:8080"},
        "ws://example.com/",
        "http://proxy:8080",
    ),
    (
        {"https_proxy": "http://proxy:8080"},
        "wss://example.com/",
        "http://proxy:8080",
    ),
    (
        {"socks_proxy": "http://proxy:1080"},
        "ws://example.com/",
        "socks5h://proxy:1080",
    ),
    (
        {"socks_proxy": "http://proxy:1080"},
        "wss://example.com/",
        "socks5h://proxy:1080",
    ),
    (
        {"ws_proxy": "http://proxy1:8080", "wss_proxy": "http://proxy2:8080"},
        "ws://example.com/",
        "http://proxy1:8080",
    ),
    (
        {"ws_proxy": "http://proxy1:8080", "wss_proxy": "http://proxy2:8080"},
        "wss://example.com/",
        "http://proxy2:8080",
    ),
    (
        {"http_proxy": "http://proxy1:8080", "https_proxy": "http://proxy2:8080"},
        "ws://example.com/",
        "http://proxy2:8080",
    ),
    (
        {"http_proxy": "http://proxy1:8080", "https_proxy": "http://proxy2:8080"},
        "wss://example.com/",
        "http://proxy2:8080",
    ),
    (
        {"https_proxy": "http://proxy:8080", "socks_proxy": "http://proxy:1080"},
        "ws://example.com/",
        "socks5h://proxy:1080",
    ),
    (
        {"https_proxy": "http://proxy:8080", "socks_proxy": "http://proxy:1080"},
        "wss://example.com/",
        "socks5h://proxy:1080",
    ),
    (
        {"socks_proxy": "http://proxy:1080", "no_proxy": ".local"},
        "ws://example.local/",
        None,
    ),
]


class URITests(unittest.TestCase):
    def test_parse_valid_uris(self):
        for uri, parsed in VALID_URIS:
            with self.subTest(uri=uri):
                self.assertEqual(parse_uri(uri), parsed)

    def test_parse_invalid_uris(self):
        for uri in INVALID_URIS:
            with self.subTest(uri=uri):
                with self.assertRaises(InvalidURI):
                    parse_uri(uri)

    def test_parse_resource_name(self):
        for uri, resource_name in URIS_WITH_RESOURCE_NAMES:
            with self.subTest(uri=uri):
                self.assertEqual(parse_uri(uri).resource_name, resource_name)

    def test_parse_user_info(self):
        for uri, user_info in URIS_WITH_USER_INFO:
            with self.subTest(uri=uri):
                self.assertEqual(parse_uri(uri).user_info, user_info)

    def test_parse_valid_proxies(self):
        for proxy, parsed in VALID_PROXIES:
            with self.subTest(proxy=proxy):
                self.assertEqual(parse_proxy(proxy), parsed)

    def test_parse_invalid_proxies(self):
        for proxy in INVALID_PROXIES:
            with self.subTest(proxy=proxy):
                with self.assertRaises(InvalidProxy):
                    parse_proxy(proxy)

    def test_parse_proxy_user_info(self):
        for proxy, user_info in PROXIES_WITH_USER_INFO:
            with self.subTest(proxy=proxy):
                self.assertEqual(parse_proxy(proxy).user_info, user_info)

    def test_get_proxy(self):
        for environ, uri, proxy in PROXY_ENVS:
            with patch.dict(os.environ, environ):
                with self.subTest(environ=environ, uri=uri):
                    self.assertEqual(get_proxy(parse_uri(uri)), proxy)
