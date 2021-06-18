import email.utils
import os
import platform
import time
import unittest


DATE = email.utils.formatdate(usegmt=True)


# Unit for timeouts. May be increased on slow machines by setting the
# WEBSOCKETS_TESTS_TIMEOUT_FACTOR environment variable.
MS = 0.001 * int(os.environ.get("WEBSOCKETS_TESTS_TIMEOUT_FACTOR", 1))

# PyPy has a performance penalty for this test suite.
if platform.python_implementation() == "PyPy":  # pragma: no cover
    MS *= 5

# asyncio's debug mode has a 10x performance penalty for this test suite.
if os.environ.get("PYTHONASYNCIODEBUG"):  # pragma: no cover
    MS *= 10

# Ensure that timeouts are larger than the clock's resolution (for Windows).
MS = max(MS, 2.5 * time.get_clock_info("monotonic").resolution)


class GeneratorTestCase(unittest.TestCase):
    def assertGeneratorRunning(self, gen):
        """
        Check that a generator-based coroutine hasn't completed yet.

        """
        next(gen)

    def assertGeneratorReturns(self, gen):
        """
        Check that a generator-based coroutine completes and return its value.

        """
        with self.assertRaises(StopIteration) as raised:
            next(gen)
        return raised.exception.value
