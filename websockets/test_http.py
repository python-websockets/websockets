import asyncio
import unittest

from .http import *
from .http import read_message  # private API


class HTTPTests(unittest.TestCase):

    def setUp(self):
        super().setUp()
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.stream = asyncio.StreamReader(loop=self.loop)

    def tearDown(self):
        self.loop.close()
        super().tearDown()

    def test_read_request(self):
        # Example from the protocol overview in RFC 6455
        self.stream.feed_data(
            b'GET /chat HTTP/1.1\r\n'
            b'Host: server.example.com\r\n'
            b'Upgrade: websocket\r\n'
            b'Connection: Upgrade\r\n'
            b'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n'
            b'Origin: http://example.com\r\n'
            b'Sec-WebSocket-Protocol: chat, superchat\r\n'
            b'Sec-WebSocket-Version: 13\r\n'
            b'\r\n'
        )
        path, hdrs = self.loop.run_until_complete(read_request(self.stream))
        self.assertEqual(path, '/chat')
        self.assertEqual(hdrs['Upgrade'], 'websocket')

    def test_read_response(self):
        # Example from the protocol overview in RFC 6455
        self.stream.feed_data(
            b'HTTP/1.1 101 Switching Protocols\r\n'
            b'Upgrade: websocket\r\n'
            b'Connection: Upgrade\r\n'
            b'Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=\r\n'
            b'Sec-WebSocket-Protocol: chat\r\n'
            b'\r\n'
        )
        status, hdrs = self.loop.run_until_complete(read_response(self.stream))
        self.assertEqual(status, 101)
        self.assertEqual(hdrs['Upgrade'], 'websocket')

    def test_method(self):
        self.stream.feed_data(b'OPTIONS * HTTP/1.1\r\n\r\n')
        with self.assertRaises(ValueError):
            self.loop.run_until_complete(read_request(self.stream))

    def test_version(self):
        self.stream.feed_data(b'GET /chat HTTP/1.0\r\n\r\n')
        with self.assertRaises(ValueError):
            self.loop.run_until_complete(read_request(self.stream))
        self.stream.feed_data(b'HTTP/1.0 400 Bad Request\r\n\r\n')
        with self.assertRaises(ValueError):
            self.loop.run_until_complete(read_response(self.stream))

    def test_headers_limit(self):
        self.stream.feed_data(b'foo: bar\r\n' * 500 + b'\r\n')
        with self.assertRaises(ValueError):
            self.loop.run_until_complete(read_message(self.stream))

    def test_line_limit(self):
        self.stream.feed_data(b'a' * 5000 + b'\r\n\r\n')
        with self.assertRaises(ValueError):
            self.loop.run_until_complete(read_message(self.stream))

    def test_line_ending(self):
        self.stream.feed_data(b'GET / HTTP/1.1\n\n')
        with self.assertRaises(ValueError):
            self.loop.run_until_complete(read_message(self.stream))
