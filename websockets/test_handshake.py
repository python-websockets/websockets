import unittest

from .exceptions import InvalidHandshake
from .handshake import *
from .handshake import accept       # private API


class HandshakeTests(unittest.TestCase):

    def test_accept(self):
        # Test vector from RFC 6455
        key = "dGhlIHNhbXBsZSBub25jZQ=="
        acc = "s3pPLMBiTxaQ9kYGzzhZRbK+xOo="
        self.assertEqual(accept(key), acc)

    def test_round_trip(self):
        request_headers = {}
        request_key = build_request(request_headers.__setitem__)
        response_key = check_request(request_headers.__getitem__)
        self.assertEqual(request_key, response_key)
        response_headers = {}
        build_response(response_headers.__setitem__, response_key)
        check_response(response_headers.__getitem__, request_key)

    def test_bad_request(self):
        headers = {}
        build_request(headers.__setitem__)
        del headers['Sec-WebSocket-Key']
        with self.assertRaises(InvalidHandshake):
            check_request(headers.__getitem__)

    def test_bad_response(self):
        headers = {}
        build_response(headers.__setitem__, 'blabla')
        del headers['Sec-WebSocket-Accept']
        with self.assertRaises(InvalidHandshake):
            check_response(headers.__getitem__, 'blabla')
