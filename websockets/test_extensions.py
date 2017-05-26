import unittest

from .extensions import PerMessageDeflate, parse_extensions
from .framing import OP_CONT, OP_PING, OP_TEXT, Frame


class ExtensionParsingTests(unittest.TestCase):
    def test_simple(self):
        self.assert_parse_extensions('permessage-deflate', [
            ('permessage-deflate', {})
        ])

    def test_one_extension_no_value(self):
        self.assert_parse_extensions(
            'permessage-deflate; client_max_window_bits', [
                ('permessage-deflate', {'client_max_window_bits': None})
            ])

    def test_one_extension_value(self):
        self.assert_parse_extensions(
            'permessage-deflate; server_max_window_bits=10', [
                ('permessage-deflate', {'server_max_window_bits': '10'})
            ])

    def test_one_extension_quoted_value(self):
        self.assert_parse_extensions(
            'permessage-deflate; server_max_window_bits="10"', [
                ('permessage-deflate', {'server_max_window_bits': '10'})
            ])

    def test_one_extension_multiple_params(self):
        self.assert_parse_extensions(
            'permessage-deflate; option_a;option_b="10";option_c=foo',
            [
                ('permessage-deflate', {
                    'option_a': None,
                    'option_b': '10',
                    'option_c': 'foo'
                })
            ])

    def test_multi_extensions(self):
        self.assert_parse_extensions(
            'ext_one; option_a;option_b="10", ext_two, ext_three; foo; bar=42',
            [
                ('ext_one', {
                    'option_a': None,
                    'option_b': '10'
                }),
                ('ext_two', {}),
                ('ext_three', {
                    'foo': None,
                    'bar': '42'
                })
            ])

    def test_multi_line(self):
        self.assert_parse_extensions(
            '\next_one, \next_two, \n\next_three; foo; bar=42',
            [
                ('ext_one', {}),
                ('ext_two', {}),
                ('ext_three', {
                    'foo': None,
                    'bar': '42'
                })
            ])

    @staticmethod
    def assert_parse_extensions(header, expected):
        result = parse_extensions(header)
        assert result == expected


class PerMessageDeflateTests(unittest.TestCase):
    def test_deflate_default(self):
        server_deflate = PerMessageDeflate(False, {})
        data = "Hello world".encode('utf-8')

        frame = Frame(True, OP_TEXT, data)
        frame = server_deflate.encode(frame)
        self.assertTrue(frame.rsv1)
        self.assertNotEqual(frame.data, data)

        frame = server_deflate.decode(frame)
        self.assertFalse(frame.rsv1)
        self.assertEqual(frame.data, data)

    def test_deflate_control(self):
        server_deflate = PerMessageDeflate(False, {})

        frame = Frame(True, OP_PING, b'foo')
        encoded = server_deflate.encode(frame)
        self.assertEqual(frame, encoded)

        decoded = server_deflate.decode(encoded)
        self.assertEqual(frame, decoded)

    def test_deflate_decode_uncompressed(self):
        server_deflate = PerMessageDeflate(False, {})
        data = "Hello world".encode('utf-8')

        frame = Frame(True, OP_TEXT, data)
        frame = server_deflate.decode(frame)
        self.assertEqual(frame.data, data)

    def test_deflate_decode_uncompressed_fragments(self):
        server_deflate = PerMessageDeflate(False, {})
        data = "Hello world".encode('utf-8')

        frame = Frame(True, OP_TEXT, data)
        frag1 = server_deflate.decode(
            frame._replace(fin=False, data=frame.data[:5])
        )
        frag2 = server_deflate.decode(
            frame._replace(opcode=OP_CONT, data=frame.data[5:])
        )
        result = frag1.data + frag2.data
        self.assertEqual(result, data)

    def test_deflate_fragment(self):
        server_deflate = PerMessageDeflate(False, {})
        data = "I love websockets, especially RFC 7692".encode('utf-8')

        frame = server_deflate.encode(Frame(True, OP_TEXT, data))
        frag1 = server_deflate.decode(
            frame._replace(fin=False, data=frame.data[:5])
        )
        frag2 = server_deflate.decode(
            frame._replace(fin=False, rsv1=False, opcode=OP_CONT,
                           data=frame.data[5:10])
        )
        frag3 = server_deflate.decode(
            frame._replace(rsv1=False, opcode=OP_CONT, data=frame.data[10:])
        )
        result = frag1.data + frag2.data + frag3.data
        self.assertEqual(result, data)

    # Manually configured items

    def test_deflate_response_server_no_context_takeover(self):
        deflate = PerMessageDeflate(False, {}, server_no_context_takeover=True)
        self.assertIn('server_no_context_takeover', deflate.response())

    def test_deflate_response_client_no_context_takeover(self):
        deflate = PerMessageDeflate(False, {}, client_no_context_takeover=True)
        self.assertIn('client_no_context_takeover', deflate.response())

    def test_deflate_response_client_max_window_bits(self):
        deflate = PerMessageDeflate(False, {}, client_max_window_bits=10)
        self.assertIn('client_max_window_bits=10', deflate.response())

    def test_deflate_response_server_max_window_bits(self):
        deflate = PerMessageDeflate(False, {}, server_max_window_bits=8)
        self.assertIn('server_max_window_bits=8', deflate.response())

    # Taking requested params into account

    def test_deflate_server_max_window_bits_same(self):
        deflate = PerMessageDeflate(False, {
            'server_max_window_bits': 10
        }, server_max_window_bits=10)
        self.assertIn('server_max_window_bits=10', deflate.response())

    def test_deflate_server_max_window_bits_higher(self):
        deflate = PerMessageDeflate(False, {
            'server_max_window_bits': 12
        }, server_max_window_bits=10)
        self.assertIn('server_max_window_bits=10', deflate.response())

    def test_deflate_server_max_window_bits_lower(self):
        deflate = PerMessageDeflate(False, {
            'server_max_window_bits': 8
        }, server_max_window_bits=10)
        self.assertIn('server_max_window_bits=8', deflate.response())

    def test_deflate_client_max_window_bits_same(self):
        deflate = PerMessageDeflate(False, {
            'client_max_window_bits': 10
        }, client_max_window_bits=10)
        self.assertIn('client_max_window_bits=10', deflate.response())

    def test_deflate_client_max_window_bits_higher(self):
        deflate = PerMessageDeflate(False, {
            'client_max_window_bits': 12
        }, client_max_window_bits=10)
        self.assertIn('client_max_window_bits=10', deflate.response())

    def test_deflate_client_max_window_bits_lower(self):
        deflate = PerMessageDeflate(False, {
            'client_max_window_bits': 8
        }, client_max_window_bits=10)
        self.assertIn('client_max_window_bits=8', deflate.response())

    def test_deflate_server_no_context_takeover(self):
        deflate = PerMessageDeflate(False, {
            'server_no_context_takeover': None
        })
        self.assertIn('server_no_context_takeover', deflate.response())

    def test_deflate_server_no_context_takeover_invalid(self):
        with self.assertRaises(Exception):
            PerMessageDeflate(False, {
                'server_no_context_takeover': 42
            })

    def test_deflate_client_no_context_takeover(self):
        deflate = PerMessageDeflate(False, {
            'client_no_context_takeover': None
        })
        self.assertIn('client_no_context_takeover', deflate.response())

    def test_deflate_client_no_context_takeover_invalid(self):
        with self.assertRaises(Exception):
            PerMessageDeflate(False, {
                'client_no_context_takeover': 42
            })

    def test_deflate_invalid_parameter(self):
        with self.assertRaises(Exception):
            PerMessageDeflate(False, {
                'websockets_are_great': 42
            })
