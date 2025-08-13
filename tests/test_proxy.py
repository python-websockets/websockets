import os
import unittest
from unittest.mock import patch

from websockets.exceptions import InvalidProxy
from websockets.http11 import USER_AGENT
from websockets.proxy import *
from websockets.proxy import prepare_connect_request
from websockets.uri import parse_uri


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

CONNECT_REQUESTS = [
    (
        {"https_proxy": "http://proxy:8080"},
        "ws://example.com/",
        (
            b"CONNECT example.com:80 HTTP/1.1\r\nHost: example.com\r\n"
            b"User-Agent: " + USER_AGENT.encode() + b"\r\n\r\n"
        ),
    ),
    (
        {"https_proxy": "http://proxy:8080"},
        "wss://example.com/",
        (
            b"CONNECT example.com:443 HTTP/1.1\r\nHost: example.com\r\n"
            b"User-Agent: " + USER_AGENT.encode() + b"\r\n\r\n"
        ),
    ),
    (
        {"https_proxy": "http://hello:iloveyou@proxy:8080"},
        "ws://example.com/",
        (
            b"CONNECT example.com:80 HTTP/1.1\r\nHost: example.com\r\n"
            b"User-Agent: " + USER_AGENT.encode() + b"\r\n"
            b"Proxy-Authorization: Basic aGVsbG86aWxvdmV5b3U=\r\n\r\n"
        ),
    ),
]

CONNECT_REQUESTS_WITH_USER_AGENT = [
    (
        "Smith",
        (
            b"CONNECT example.com:80 HTTP/1.1\r\nHost: example.com\r\n"
            b"User-Agent: Smith\r\n\r\n"
        ),
    ),
    (
        None,
        b"CONNECT example.com:80 HTTP/1.1\r\nHost: example.com\r\n\r\n",
    ),
]


class ProxyTests(unittest.TestCase):
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

    def test_prepare_connect_request(self):
        for environ, uri, request in CONNECT_REQUESTS:
            with patch.dict(os.environ, environ):
                with self.subTest(environ=environ, uri=uri):
                    uri = parse_uri(uri)
                    proxy = parse_proxy(get_proxy(uri))
                    self.assertEqual(prepare_connect_request(proxy, uri), request)

    def test_prepare_connect_request_with_user_agent(self):
        for user_agent_header, request in CONNECT_REQUESTS_WITH_USER_AGENT:
            with self.subTest(user_agent_header=user_agent_header):
                uri = parse_uri("ws://example.com")
                proxy = parse_proxy("http://proxy:8080")
                self.assertEqual(
                    prepare_connect_request(proxy, uri, user_agent_header),
                    request,
                )
