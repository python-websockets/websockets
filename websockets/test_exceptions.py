import unittest

from .exceptions import InvalidStatus


class InvalidStatusTests(unittest.TestCase):

    def test_str(self):
        exc = InvalidStatus(403, reason='Forbidden')
        self.assertEqual(str(exc), 'Bad status code: 403 (Forbidden)')

    def test_str_no_reason(self):
        exc = InvalidStatus(400)
        self.assertEqual(str(exc), 'Bad status code: 400')
