import logging
try:
    import ssl
except ImportError:
    ssl = None
import unittest
from unittest.mock import patch

import tulip

from . import client
from .client import *
from .exceptions import InvalidHandshake
from . import server
from .server import *


@tulip.coroutine
def echo(ws, uri):
    ws.send((yield from ws.recv()))


class ClientServerTests(unittest.TestCase):

    def setUp(self):
        self.loop = tulip.new_event_loop()
        tulip.set_event_loop(self.loop)
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

    def test_server_receives_malformed_request(self):
        old_read_request = server.read_request
        @tulip.coroutine
        def read_request(stream):
            yield from old_read_request(stream)
            raise ValueError("Not sure what went wrong")
        server.read_request = read_request
        server.logger.setLevel(logging.ERROR)
        try:
            with self.assertRaises(InvalidHandshake):
                self.start_client()
        finally:
            server.read_request = old_read_request
            server.logger.setLevel(logging.NOTSET)

    def test_client_receives_malformed_response(self):
        old_read_response = client.read_response
        @tulip.coroutine
        def read_response(stream):
            yield from old_read_response(stream)
            raise ValueError("Not sure what went wrong")
        client.read_response = read_response
        try:
            with self.assertRaises(InvalidHandshake):
                self.start_client()
        finally:
            client.read_response = old_read_response

    def test_client_sends_invalid_handshake_request(self):
        old_build_request = client.build_request
        def build_request(set_header):
            old_build_request(set_header)
            return '42'                                     # Use a wrong key.
        client.build_request = build_request
        try:
            with self.assertRaises(InvalidHandshake):
                self.start_client()
        finally:
            client.build_request = old_build_request

    def test_server_sends_invalid_handshake_response(self):
        old_build_response = server.build_response
        def build_response(set_header, key):
            old_build_response(set_header, '42')            # Use a wrong key.
        server.build_response = build_response
        try:
            with self.assertRaises(InvalidHandshake):
                self.start_client()
        finally:
            server.build_response = old_build_response

    def test_server_does_not_switch_protocols(self):
        old_read_response = client.read_response
        @tulip.coroutine
        def read_response(stream):
            code, headers = yield from old_read_response(stream)
            return 400, headers
        client.read_response = read_response
        try:
            with self.assertRaises(InvalidHandshake):
                self.start_client()
        finally:
            client.read_response = old_read_response

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


@unittest.skipIf(ssl is None, "SSL support isn't available")
class SSLClientServerTests(unittest.TestCase):

    def setUp(self):
        self.loop = tulip.new_event_loop()
        tulip.set_event_loop(self.loop)

    def tearDown(self):
        self.loop.close()

    def run_client_server_ssl(self, client_context, server_context):
        server = serve(echo, 'localhost', 8642, ssl=server_context)
        self.server = self.loop.run_until_complete(server)
        try:
            client = connect('wss://localhost:8642/', ssl=client_context)
            self.client = self.loop.run_until_complete(client)
            self.client.send("Hello!")
            reply = self.loop.run_until_complete(self.client.recv())
            self.assertEqual(reply, "Hello!")
            self.loop.run_until_complete(self.client.worker)
        finally:
            self.server.close()
            self.loop.run_until_complete(self.server.wait_closed())

    def test_valid_certificate(self):
        client_context = ssl.SSLContext(ssl.PROTOCOL_TLSv1)
        client_context.load_verify_locations('ssl/ca.pem')
        client_context.verify_mode = ssl.CERT_REQUIRED
        server_context = ssl.SSLContext(ssl.PROTOCOL_TLSv1)
        server_context.load_cert_chain(
                certfile='ssl/localhost.pem',
                keyfile='ssl/localhost.key')
        self.run_client_server_ssl(client_context, server_context)

    def test_invalid_certificate(self):
        client_context = ssl.SSLContext(ssl.PROTOCOL_TLSv1)
        client_context.load_verify_locations('ssl/ca.pem')
        client_context.verify_mode = ssl.CERT_REQUIRED
        server_context = ssl.SSLContext(ssl.PROTOCOL_TLSv1)
        server_context.load_cert_chain(
                certfile='ssl/otherhost.pem',
                keyfile='ssl/otherhost.key')
        with self.assertRaises(ssl.CertificateError):
            self.run_client_server_ssl(client_context, server_context)

    def test_invalid_certificate_not_verified(self):
        client_context = ssl.SSLContext(ssl.PROTOCOL_TLSv1)
        client_context.load_verify_locations('ssl/ca.pem')
        client_context.verify_mode = ssl.CERT_NONE
        server_context = ssl.SSLContext(ssl.PROTOCOL_TLSv1)
        server_context.load_cert_chain(
                certfile='ssl/otherhost.pem',
                keyfile='ssl/otherhost.key')
        self.run_client_server_ssl(client_context, server_context)
