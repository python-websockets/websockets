import unittest

from .utils import *


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
