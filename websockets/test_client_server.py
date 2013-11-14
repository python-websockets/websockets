import unittest
from unittest.mock import patch

import asyncio

from .client import *
from .exceptions import InvalidHandshake
from .http import read_response
from .server import *


@asyncio.coroutine
def echo(ws, uri):
    ws.send((yield from ws.recv()))


class ClientServerTests(unittest.TestCase):

    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.start_server()

    def tearDown(self):
        self.stop_server()
        self.loop.close()

    def start_server(self):
        server = serve(echo, 'localhost', 8642)
        self.server = self.loop.run_until_complete(server)

    def start_client(self):
        client = connect('ws://localhost:8642/')
        self.client = self.loop.run_until_complete(client)

    def stop_client(self):
        self.loop.run_until_complete(self.client.worker)

    def stop_server(self):
        self.server.close()
        self.loop.run_until_complete(self.server.wait_closed())

    def test_basic(self):
        self.start_client()
        self.client.send("Hello!")
        reply = self.loop.run_until_complete(self.client.recv())
        self.assertEqual(reply, "Hello!")
        self.stop_client()

    @patch('websockets.server.read_request')
    def test_server_receives_malformed_request(self, _read_request):
        _read_request.side_effect = ValueError("read_request failed")

        with self.assertRaises(InvalidHandshake):
            self.start_client()

    @patch('websockets.client.read_response')
    def test_client_receives_malformed_response(self, _read_response):
        _read_response.side_effect = ValueError("read_response failed")

        with self.assertRaises(InvalidHandshake):
            self.start_client()

    @patch('websockets.client.build_request')
    def test_client_sends_invalid_handshake_request(self, _build_request):
        def wrong_build_request(set_header):
            return '42'
        _build_request.side_effect = wrong_build_request

        with self.assertRaises(InvalidHandshake):
            self.start_client()

    @patch('websockets.server.build_response')
    def test_server_sends_invalid_handshake_response(self, _build_response):
        def wrong_build_response(set_header, key):
            return build_response(set_header, '42')
        _build_response.side_effect = wrong_build_response

        with self.assertRaises(InvalidHandshake):
            self.start_client()

    @patch('websockets.client.read_response')
    def test_server_does_not_switch_protocols(self, _read_response):
        @asyncio.coroutine
        def wrong_read_response(stream):
            code, headers = yield from read_response(stream)
            return 400, headers
        _read_response.side_effect = wrong_read_response

        with self.assertRaises(InvalidHandshake):
            self.start_client()

    @patch('websockets.server.WebSocketServerProtocol.send')
    def test_server_handler_crashes(self, send):
        send.side_effect = ValueError("send failed")

        self.start_client()
        self.client.send("Hello!")
        reply = self.loop.run_until_complete(self.client.recv())
        self.assertEqual(reply, None)
        self.stop_client()

        # Connection ends with an unexpected error.
        self.assertEqual(self.client.close_code, 1011)

    @patch('websockets.server.WebSocketServerProtocol.close')
    def test_server_close_crashes(self, close):
        close.side_effect = ValueError("close failed")

        self.start_client()
        self.client.send("Hello!")
        reply = self.loop.run_until_complete(self.client.recv())
        self.assertEqual(reply, "Hello!")
        self.stop_client()

        # Connection ends with a protocol error.
        self.assertEqual(self.client.close_code, 1002)
