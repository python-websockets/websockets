# Tests containing Python 3.5+ syntax, extracted from test_client_server.py.

import asyncio
import pathlib
import socket
import sys
import tempfile
import unittest

from ..client import *
from ..protocol import State
from ..server import *
from ..test_client_server import get_server_uri, handler


class AsyncAwaitTests(unittest.TestCase):

    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self):
        self.loop.close()

    def test_client(self):
        start_server = serve(handler, 'localhost', 0)
        server = self.loop.run_until_complete(start_server)

        async def run_client():
            # Await connect.
            client = await connect(get_server_uri(server))
            self.assertEqual(client.state, State.OPEN)
            await client.close()
            self.assertEqual(client.state, State.CLOSED)

        self.loop.run_until_complete(run_client())

        server.close()
        self.loop.run_until_complete(server.wait_closed())

    def test_server(self):

        async def run_server():
            # Await serve.
            server = await serve(handler, 'localhost', 0)
            self.assertTrue(server.sockets)
            server.close()
            await server.wait_closed()
            self.assertFalse(server.sockets)

        self.loop.run_until_complete(run_server())


class ContextManagerTests(unittest.TestCase):

    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self):
        self.loop.close()

    # Asynchronous context managers are only enabled on Python ≥ 3.5.1.
    @unittest.skipIf(
        sys.version_info[:3] <= (3, 5, 0), 'this test requires Python 3.5.1+')
    def test_client(self):
        start_server = serve(handler, 'localhost', 0)
        server = self.loop.run_until_complete(start_server)

        async def run_client():
            # Use connect as an asynchronous context manager.
            async with connect(get_server_uri(server)) as client:
                self.assertEqual(client.state, State.OPEN)

            # Check that exiting the context manager closed the connection.
            self.assertEqual(client.state, State.CLOSED)

        self.loop.run_until_complete(run_client())

        server.close()
        self.loop.run_until_complete(server.wait_closed())

    # Asynchronous context managers are only enabled on Python ≥ 3.5.1.
    @unittest.skipIf(
        sys.version_info[:3] <= (3, 5, 0), 'this test requires Python 3.5.1+')
    def test_server(self):

        async def run_server():
            # Use serve as an asynchronous context manager.
            async with serve(handler, 'localhost', 0) as server:
                self.assertTrue(server.sockets)

            # Check that exiting the context manager closed the server.
            self.assertFalse(server.sockets)

        self.loop.run_until_complete(run_server())

    # Asynchronous context managers are only enabled on Python ≥ 3.5.1.
    @unittest.skipIf(
        sys.version_info[:3] <= (3, 5, 0), 'this test requires Python 3.5.1+')
    @unittest.skipUnless(
        hasattr(socket, 'AF_UNIX'), 'this test requires Unix sockets')
    def test_unix_server(self):

        async def run_server(path):
            async with unix_serve(handler, path) as server:
                self.assertTrue(server.sockets)

            # Check that exiting the context manager closed the server.
            self.assertFalse(server.sockets)

        with tempfile.TemporaryDirectory() as temp_dir:
            path = bytes(pathlib.Path(temp_dir) / 'websockets')
            self.loop.run_until_complete(run_server(path))
