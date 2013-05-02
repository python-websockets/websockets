import unittest

import tulip

from .client import *
from .server import *


@tulip.coroutine
def echo(ws, uri):
    ws.send((yield from ws.recv()))


class ClientServerTests(unittest.TestCase):

    def setUp(self):
        self.loop = tulip.new_event_loop()
        tulip.set_event_loop(self.loop)

        server_task = serve(echo, 'localhost', 8642)
        self.sockets = self.loop.run_until_complete(server_task)

        client_coroutine = connect('ws://localhost:8642/')
        self.client = self.loop.run_until_complete(client_coroutine)

    def tearDown(self):
        self.loop.run_until_complete(self.client.wait_close())
        for socket in sockets:
            self.loop.stop_serving(socket)
        self.loop.close()

    def test_basic(self):
        self.client.send("Hello!")
        reply = self.loop.run_until_complete(self.client.recv())
        self.assertEqual(reply, "Hello!")


