import sys
import time
import unittest


try:
    import uvloop
except ImportError:
    pass


@unittest.skipUnless("uvloop" in sys.modules, "uvloop not installed")
class UVLoopTestCase(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def loop_factory():
        return uvloop.Loop()
