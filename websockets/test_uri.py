import unittest

from .exceptions import InvalidURI
from .uri import *


VALID_URIS = (
    ('ws://localhost/', (False, 'localhost', 80, '/')),
    ('wss://localhost/', (True, 'localhost', 443, '/')),
    ('ws://localhost/path?query', (False, 'localhost', 80, '/path?query')),
)

INVALID_URIS = (
    'http://localhost/',
    'https://localhost/',
    'http://localhost/path#fragment'
)


class URITests(unittest.TestCase):

    def test_success(self):
        for uri, parsed in VALID_URIS:
            self.assertEqual(parse_uri(uri), parsed)

    def test_error(self):
        for uri in INVALID_URIS:
            with self.assertRaises(InvalidURI):
                parse_uri(uri)
