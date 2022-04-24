import unittest

from websockets.sync.utils import *

from ..utils import MS


class DeadlineTests(unittest.TestCase):
    def test_timeout(self):
        deadline = Deadline(MS)
        self.assertGreater(deadline.timeout(), 0)
        self.assertLess(deadline.timeout(), MS)

    def test_no_timeout(self):
        deadline = Deadline(None)
        self.assertIsNone(deadline.timeout(), None)
