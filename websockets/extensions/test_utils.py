import unittest

from ..exceptions import InvalidHeader
from .utils import *


class UtilsTests(unittest.TestCase):

    def test_parse_extension_list(self):
        for header, parsed in [
            # Synthetic examples
            (
                'foo',
                [('foo', [])],
            ),
            (
                'foo, bar',
                [('foo', []), ('bar', [])],
            ),
            (
                'foo; name; token=token; quoted-string="quoted string", '
                'bar; quux; quuux',
                [
                    ('foo', [('name', None), ('token', 'token'),
                             ('quoted-string', 'quoted string')]),
                    ('bar', [('quux', None), ('quuux', None)]),
                ],
            ),
            # Pathological examples
            (
                'a; b="q,s;1\\"2\'3\\\\4="; c="q;s,6=7\\\\8\'9\\\""',
                [('a', [('b', 'q,s;1"2\'3\\4='), ('c', 'q;s,6=7\\8\'9"')])]
            ),
            (
                ',\t, ,  ,foo  ;bar = 42,,   baz,,',
                [('foo', [('bar', '42')]), ('baz', [])],
            ),
            # Realistic use cases for permessage-deflate
            (
                'permessage-deflate',
                [('permessage-deflate', [])],
            ),
            (
                'permessage-deflate; client_max_window_bits',
                [('permessage-deflate', [('client_max_window_bits', None)])],
            ),
            (
                'permessage-deflate; server_max_window_bits=10',
                [('permessage-deflate', [('server_max_window_bits', '10')])],
            ),
        ]:
            self.assertEqual(parse_extension_list(header), parsed)

    def test_parse_extension_list_invalid_header(self):
        for header in [
            # Truncated examples
            '',
            ',\t,'
            'foo;',
            'foo; bar;',
            'foo; bar=',
            'foo; bar="baz',
            # Wrong delimiter
            'foo, bar, baz=quux; quuux',

        ]:
            with self.assertRaises(InvalidHeader):
                parse_extension_list(header)
