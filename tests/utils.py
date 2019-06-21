import asyncio
import os
import time
import unittest


class AsyncioTestCase(unittest.TestCase):
    """
    Base class for tests that sets up an isolated event loop for each test.

    """

    def setUp(self):
        super().setUp()
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self):
        self.loop.close()
        super().tearDown()

    def run_loop_once(self):
        # Process callbacks scheduled with call_soon by appending a callback
        # to stop the event loop then running it until it hits that callback.
        self.loop.call_soon(self.loop.stop)
        self.loop.run_forever()


# Unit for timeouts. May be increased on slow machines by setting the
# WEBSOCKETS_TESTS_TIMEOUT_FACTOR environment variable.
MS = 0.001 * int(os.environ.get("WEBSOCKETS_TESTS_TIMEOUT_FACTOR", 1))

# asyncio's debug mode has a 10x performance penalty for this test suite.
if os.environ.get("PYTHONASYNCIODEBUG"):  # pragma: no cover
    MS *= 10

# Ensure that timeouts are larger than the clock's resolution (for Windows).
MS = max(MS, 2.5 * time.get_clock_info("monotonic").resolution)
