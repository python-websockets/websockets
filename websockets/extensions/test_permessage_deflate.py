import unittest

from ..framing import OP_CONT, OP_PING, OP_TEXT, Frame
from .permessage_deflate import *


class PerMessageDeflateTests(unittest.TestCase):

    def test_name(self):
        assert PerMessageDeflate.name == 'permessage-deflate'

    def test_deflate_encode_decode_text_frame(self):
        deflate = PerMessageDeflate(False, False, 15, 15)
        data = "Hello world".encode('utf-8')
        frame = Frame(True, OP_TEXT, data)

        enc_frame = deflate.encode(frame)

        self.assertTrue(enc_frame.rsv1)
        self.assertNotEqual(enc_frame.data, data)

        dec_frame = deflate.decode(enc_frame)

        self.assertFalse(dec_frame.rsv1)
        self.assertEqual(dec_frame.data, data)

    def test_deflate_no_encode_decode_control_frame(self):
        deflate = PerMessageDeflate(False, False, 15, 15)
        frame = Frame(True, OP_PING, b'')

        enc_frame = deflate.encode(frame)
        self.assertEqual(enc_frame, frame)

        dec_frame = deflate.decode(frame)
        self.assertEqual(dec_frame, frame)

    def test_deflate_no_decode_uncompressed_text_frame(self):
        deflate = PerMessageDeflate(False, False, 15, 15)
        data = "Hello world".encode('utf-8')
        frame = Frame(True, OP_TEXT, data)

        dec_frame = deflate.decode(frame)

        self.assertEqual(dec_frame, frame)

    # def test_deflate_decode_uncompressed_fragments(self):
    #     deflate = PerMessageDeflate(False, False, 15, 15)
    #     data = "Hello world".encode('utf-8')

    #     frame = Frame(True, OP_TEXT, data)
    #     frag1 = deflate.decode(
    #         frame._replace(fin=False, data=frame.data[:5])
    #     )
    #     frag2 = deflate.decode(
    #         frame._replace(opcode=OP_CONT, data=frame.data[5:])
    #     )
    #     result = frag1.data + frag2.data
    #     self.assertEqual(result, data)

    # def test_deflate_fragment(self):
    #     deflate = PerMessageDeflate(False, False, 15, 15)
    #     data = "I love websockets, especially RFC 7692".encode('utf-8')

    #     frame = deflate.encode(Frame(True, OP_TEXT, data))
    #     frag1 = deflate.decode(
    #         frame._replace(fin=False, data=frame.data[:5])
    #     )
    #     frag2 = deflate.decode(
    #         frame._replace(fin=False, rsv1=False, opcode=OP_CONT,
    #                        data=frame.data[5:10])
    #     )
    #     frag3 = deflate.decode(
    #         frame._replace(rsv1=False, opcode=OP_CONT, data=frame.data[10:])
    #     )
    #     result = frag1.data + frag2.data + frag3.data
    #     self.assertEqual(result, data)

    # # Manually configured items

    # def test_deflate_response_server_no_context_takeover(self):
    #     deflate = PerMessageDeflate(False, False, None, None, server_no_context_takeover=True)
    #     self.assertIn('server_no_context_takeover', deflate.response())

    # def test_deflate_response_client_no_context_takeover(self):
    #     deflate = PerMessageDeflate(False, False, None, None, client_no_context_takeover=True)
    #     self.assertIn('client_no_context_takeover', deflate.response())

    # def test_deflate_response_client_max_window_bits(self):
    #     deflate = PerMessageDeflate(False, False, None, None, client_max_window_bits=10)
    #     self.assertIn('client_max_window_bits=10', deflate.response())

    # def test_deflate_response_server_max_window_bits(self):
    #     deflate = PerMessageDeflate(False, False, None, None, server_max_window_bits=8)
    #     self.assertIn('server_max_window_bits=8', deflate.response())

    # # Taking requested params into account

    # def test_deflate_server_max_window_bits_same(self):
    #     deflate = PerMessageDeflate(False, {
    #         'server_max_window_bits': 10
    #     }, server_max_window_bits=10)
    #     self.assertIn('server_max_window_bits=10', deflate.response())

    # def test_deflate_server_max_window_bits_higher(self):
    #     deflate = PerMessageDeflate(False, {
    #         'server_max_window_bits': 12
    #     }, server_max_window_bits=10)
    #     self.assertIn('server_max_window_bits=10', deflate.response())

    # def test_deflate_server_max_window_bits_lower(self):
    #     deflate = PerMessageDeflate(False, {
    #         'server_max_window_bits': 8
    #     }, server_max_window_bits=10)
    #     self.assertIn('server_max_window_bits=8', deflate.response())

    # def test_deflate_client_max_window_bits_same(self):
    #     deflate = PerMessageDeflate(False, {
    #         'client_max_window_bits': 10
    #     }, client_max_window_bits=10)
    #     self.assertIn('client_max_window_bits=10', deflate.response())

    # def test_deflate_client_max_window_bits_higher(self):
    #     deflate = PerMessageDeflate(False, {
    #         'client_max_window_bits': 12
    #     }, client_max_window_bits=10)
    #     self.assertIn('client_max_window_bits=10', deflate.response())

    # def test_deflate_client_max_window_bits_lower(self):
    #     deflate = PerMessageDeflate(False, {
    #         'client_max_window_bits': 8
    #     }, client_max_window_bits=10)
    #     self.assertIn('client_max_window_bits=8', deflate.response())

    # def test_deflate_server_no_context_takeover(self):
    #     deflate = PerMessageDeflate(False, {
    #         'server_no_context_takeover': None
    #     })
    #     self.assertIn('server_no_context_takeover', deflate.response())

    # def test_deflate_server_no_context_takeover_invalid(self):
    #     with self.assertRaises(Exception):
    #         PerMessageDeflate(False, {
    #             'server_no_context_takeover': 42
    #         })

    # def test_deflate_client_no_context_takeover(self):
    #     deflate = PerMessageDeflate(False, {
    #         'client_no_context_takeover': None
    #     })
    #     self.assertIn('client_no_context_takeover', deflate.response())

    # def test_deflate_client_no_context_takeover_invalid(self):
    #     with self.assertRaises(Exception):
    #         PerMessageDeflate(False, {
    #             'client_no_context_takeover': 42
    #         })

    # def test_deflate_invalid_parameter(self):
    #     with self.assertRaises(Exception):
    #         PerMessageDeflate(False, {
    #             'websockets_are_great': 42
    #         })
