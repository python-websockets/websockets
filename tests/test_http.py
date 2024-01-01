import unittest

from websockets.http import *


class HTTPTests(unittest.TestCase):
    def test_user_agent(self):
        USER_AGENT  # exists
