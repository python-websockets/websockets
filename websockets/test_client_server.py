import logging
import unittest
import unittest.mock

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
        server_task = serve(echo, 'localhost', 8642)
        self.sockets = self.loop.run_until_complete(server_task)

    def start_client(self):
        client_coroutine = connect('ws://localhost:8642/')
        self.client = self.loop.run_until_complete(client_coroutine)

    def stop_client(self):
        self.loop.run_until_complete(self.client.close_waiter)

    def stop_server(self):
        for socket in self.sockets:
            self.loop.stop_serving(socket)

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
