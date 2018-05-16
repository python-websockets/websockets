import unittest

from .exceptions import InvalidHeaderFormat
from .headers import *


class HeadersTests(unittest.TestCase):

    def test_parse_connection(self):
        for header, parsed in [
            # Realistic use cases
            (
                'Upgrade',                  # Safari, Chrome
                ['Upgrade'],
            ),
            (
                'keep-alive, Upgrade',      # Firefox
                ['keep-alive', 'Upgrade'],
            ),
            # Pathological example
            (
                ',,\t,  , ,Upgrade  ,,',
                ['Upgrade'],
            ),
        ]:
            with self.subTest(header=header):
                self.assertEqual(parse_connection(header), parsed)

    def test_parse_connection_invalid_header(self):
        for header in [
            '???',
            'keep-alive; Upgrade',
        ]:
            with self.subTest(header=header):
                with self.assertRaises(InvalidHeaderFormat):
                    parse_connection(header)

    def test_parse_upgrade(self):
        for header, parsed in [
            # Realistic use case
            (
                'websocket',
                ['websocket'],
            ),
            # Synthetic example
            (
                'http/3.0, websocket',
                ['http/3.0', 'websocket']
            ),
            # Pathological example
            (
                ',,  WebSocket,  \t,,',
                ['WebSocket'],
            ),
        ]:
            with self.subTest(header=header):
                self.assertEqual(parse_upgrade(header), parsed)

    def test_parse_upgrade_invalid_header(self):
        for header in [
            '???',
            'websocket 2',
            'http/3.0; websocket',
        ]:
            with self.subTest(header=header):
                with self.assertRaises(InvalidHeaderFormat):
                    parse_upgrade(header)

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
                'foo; name; token=token; quoted-string="quoted-string", '
                'bar; quux; quuux',
                [
                    ('foo', [('name', None), ('token', 'token'),
                             ('quoted-string', 'quoted-string')]),
                    ('bar', [('quux', None), ('quuux', None)]),
                ],
            ),
            # Pathological example
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
            with self.subTest(header=header):
                self.assertEqual(parse_extension_list(header), parsed)
                # Also ensure that build_extension_list round-trips cleanly.
                unparsed = build_extension_list(parsed)
                self.assertEqual(parse_extension_list(unparsed), parsed)

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
            # Value in quoted string parameter that isn't a token
            'foo; bar=" "',
        ]:
            with self.subTest(header=header):
                with self.assertRaises(InvalidHeaderFormat):
                    parse_extension_list(header)

    def test_parse_subprotocol_list(self):
        for header, parsed in [
            # Synthetic examples
            (
                'foo',
                ['foo'],
            ),
            (
                'foo, bar',
                ['foo', 'bar'],
            ),
            # Pathological example
            (
                ',\t, ,  ,foo  ,,   bar,baz,,',
                ['foo', 'bar', 'baz'],
            ),
        ]:
            with self.subTest(header=header):
                self.assertEqual(parse_subprotocol_list(header), parsed)
                # Also ensure that build_subprotocol_list round-trips cleanly.
                unparsed = build_subprotocol_list(parsed)
                self.assertEqual(parse_subprotocol_list(unparsed), parsed)

    def test_parse_subprotocol_list_invalid_header(self):
        for header in [
            # Truncated examples
            '',
            ',\t,'
            # Wrong delimiter
            'foo; bar',
        ]:
            with self.subTest(header=header):
                with self.assertRaises(InvalidHeaderFormat):
                    parse_subprotocol_list(header)
