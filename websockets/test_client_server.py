import logging
import os
import ssl
import unittest
from unittest.mock import patch

import asyncio

from .client import *
from .exceptions import InvalidHandshake
from .http import read_response, USER_AGENT
from .server import *


# Avoid displaying stack traces at the ERROR logging level.
logging.basicConfig(level=logging.CRITICAL)

testcert = os.path.join(os.path.dirname(__file__), 'testcert.pem')


@asyncio.coroutine
def handler(ws, path):
    if path == '/attributes':
        yield from ws.send(repr((ws.host, ws.port, ws.secure)))
    elif path == '/raw_headers':
        yield from ws.send(repr(ws.raw_request_headers))
        yield from ws.send(repr(ws.raw_response_headers))
    else:
        yield from ws.send((yield from ws.recv()))


class ClientServerTests(unittest.TestCase):

    secure = False

    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.start_server()

    def tearDown(self):
        self.stop_server()
        self.loop.close()

    def start_server(self):
        server = serve(handler, 'localhost', 8642)
        self.server = self.loop.run_until_complete(server)

    def start_client(self, path=''):
        client = connect('ws://localhost:8642/' + path)
        self.client = self.loop.run_until_complete(client)

    def stop_client(self):
        self.loop.run_until_complete(self.client.worker)

    def stop_server(self):
        self.server.close()
        self.loop.run_until_complete(self.server.wait_closed())

    def test_basic(self):
        self.start_client()
        self.loop.run_until_complete(self.client.send("Hello!"))
        reply = self.loop.run_until_complete(self.client.recv())
        self.assertEqual(reply, "Hello!")
        self.stop_client()

    def test_protocol_attributes(self):
        self.start_client('attributes')
        expected_attrs = ('localhost', 8642, self.secure)
        client_attrs = (self.client.host, self.client.port, self.client.secure)
        self.assertEqual(client_attrs, expected_attrs)
        server_attrs = self.loop.run_until_complete(self.client.recv())
        self.assertEqual(server_attrs, repr(expected_attrs))
        self.stop_client()

    def test_protocol_raw_headers(self):
        self.start_client('raw_headers')
        client_req = self.client.raw_request_headers
        client_resp = self.client.raw_response_headers
        self.assertEqual(dict(client_req)['User-Agent'], USER_AGENT)
        self.assertEqual(dict(client_resp)['Server'], USER_AGENT)
        server_req = self.loop.run_until_complete(self.client.recv())
        server_resp = self.loop.run_until_complete(self.client.recv())
        self.assertEqual(server_req, repr(client_req))
        self.assertEqual(server_resp, repr(client_resp))
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

        # Now the server believes the connection is open. Run the event loop
        # once to make it notice the connection was closed. Interesting hack.
        self.loop.run_until_complete(asyncio.sleep(0))

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

        # Now the server believes the connection is open. Run the event loop
        # once to make it notice the connection was closed. Interesting hack.
        self.loop.run_until_complete(asyncio.sleep(0))

    @patch('websockets.server.WebSocketServerProtocol.send')
    def test_server_handler_crashes(self, send):
        send.side_effect = ValueError("send failed")

        self.start_client()
        self.loop.run_until_complete(self.client.send("Hello!"))
        reply = self.loop.run_until_complete(self.client.recv())
        self.assertEqual(reply, None)
        self.stop_client()

        # Connection ends with an unexpected error.
        self.assertEqual(self.client.close_code, 1011)

    @patch('websockets.server.WebSocketServerProtocol.close')
    def test_server_close_crashes(self, close):
        close.side_effect = ValueError("close failed")

        self.start_client()
        self.loop.run_until_complete(self.client.send("Hello!"))
        reply = self.loop.run_until_complete(self.client.recv())
        self.assertEqual(reply, "Hello!")
        self.stop_client()

        # Connection ends with an abnormal closure.
        self.assertEqual(self.client.close_code, 1006)


@unittest.skipUnless(os.path.exists(testcert), "test certificate is missing")
class SSLClientServerTests(ClientServerTests):

    secure = True

    @property
    def server_context(self):
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLSv1)
        ssl_context.load_cert_chain(testcert)
        return ssl_context

    @property
    def client_context(self):
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLSv1)
        ssl_context.load_verify_locations(testcert)
        ssl_context.verify_mode = ssl.CERT_REQUIRED
        return ssl_context

    def start_server(self):
        server = serve(handler, 'localhost', 8642, ssl=self.server_context)
        self.server = self.loop.run_until_complete(server)

    def start_client(self, path=''):
        client = connect('wss://localhost:8642/' + path, ssl=self.client_context)
        self.client = self.loop.run_until_complete(client)

    def test_ws_uri_is_rejected(self):
        client = connect('ws://localhost:8642/', ssl=self.client_context)
        with self.assertRaises(ValueError):
            self.loop.run_until_complete(client)

class ClientServerOriginTests(unittest.TestCase):

    def test_checking_origin_succeeds(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        server = loop.run_until_complete(
            serve(handler, 'localhost', 8642, origins=['http://localhost']))
        client = loop.run_until_complete(
            connect('ws://localhost:8642/', origin='http://localhost'))

        loop.run_until_complete(client.send("Hello!"))
        self.assertEqual(loop.run_until_complete(client.recv()), "Hello!")

        server.close()
        loop.run_until_complete(server.wait_closed())
        loop.run_until_complete(client.worker)
        loop.close()

    def test_checking_origin_fails(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        server = loop.run_until_complete(
            serve(handler, 'localhost', 8642, origins=['http://localhost']))
        with self.assertRaises(InvalidHandshake):
            loop.run_until_complete(
                connect('ws://localhost:8642/', origin='http://otherhost'))

        server.close()
        loop.run_until_complete(server.wait_closed())
        loop.close()

    def test_checking_lack_of_origin_succeeds(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        server = loop.run_until_complete(
            serve(handler, 'localhost', 8642, origins=['']))
        client = loop.run_until_complete(connect('ws://localhost:8642/'))

        loop.run_until_complete(client.send("Hello!"))
        self.assertEqual(loop.run_until_complete(client.recv()), "Hello!")

        server.close()
        loop.run_until_complete(server.wait_closed())
        loop.run_until_complete(client.worker)
        loop.close()
