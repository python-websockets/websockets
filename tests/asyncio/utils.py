import sys
import time
import unittest


try:
    import uvloop
except ImportError:
    pass
else:

    class AccurateClockLoop(uvloop.Loop):
        """
        Workaround for https://github.com/MagicStack/uvloop/issues/359.

        uvloop.Loop.time() has 1ms resolution, making latency measurements
        on localhost come out as 0 in tests. Use a real clock instead.

        """

        def time(self):
            return time.perf_counter()


def requires_accurate_clock(test):
    setattr(test, "requires_accurate_clock", True)
    return test


@unittest.skipUnless("uvloop" in sys.modules, "uvloop not installed")
class UVLoopTestCase(unittest.IsolatedAsyncioTestCase):
    def loop_factory(self):
        test_method = getattr(type(self), self._testMethodName)
        if getattr(test_method, "requires_accurate_clock", False):
            return AccurateClockLoop()
        return uvloop.Loop()
