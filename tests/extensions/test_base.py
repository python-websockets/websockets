import unittest

from websockets.extensions.base import *
from websockets.frames import TEXT, Frame


class ExtensionTests(unittest.TestCase):
    def test_encode(self):
        with self.assertRaises(NotImplementedError):
            Extension().encode(Frame(TEXT, b""))

    def test_decode(self):
        with self.assertRaises(NotImplementedError):
            Extension().decode(Frame(TEXT, b""))


class ClientExtensionFactoryTests(unittest.TestCase):
    def test_get_request_params(self):
        with self.assertRaises(NotImplementedError):
            ClientExtensionFactory().get_request_params()

    def test_process_response_params(self):
        with self.assertRaises(NotImplementedError):
            ClientExtensionFactory().process_response_params([], [])


class ServerExtensionFactoryTests(unittest.TestCase):
    def test_process_request_params(self):
        with self.assertRaises(NotImplementedError):
            ServerExtensionFactory().process_request_params([], [])
