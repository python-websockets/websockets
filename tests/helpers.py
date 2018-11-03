import asyncio
import contextlib
import functools

from websockets.compatibility import asyncio_ensure_future


class AsyncMixin:
    """
    Mixin making it easier to test with asyncio.

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

    def ensure_future(self, *args, **kwargs):
        return asyncio_ensure_future(*args, loop=self.loop, **kwargs)

    @contextlib.contextmanager
    def assertCompletesWithin(self, min_time, max_time):
        t0 = self.loop.time()
        yield
        t1 = self.loop.time()
        dt = t1 - t0
        self.assertGreaterEqual(dt, min_time, "Too fast: {} < {}".format(dt, min_time))
        self.assertLess(dt, max_time, "Too slow: {} >= {}".format(dt, max_time))


class StreamReader:
    """
    Generator-based stream reader.

    This class mirrors the API of :class:`asyncio.StreamReader` and provides a
    subset of its functionality without depending on :mod:`asyncio`.

    """

    def __init__(self):
        self.buffer = bytearray()
        self.eof = False

    def readline(self):
        # /!\ doesn't support concurrent calls /!\
        n = 0  # number of bytes to read
        p = 0  # number of bytes without a newline
        while True:
            n = self.buffer.find(b'\n', p) + 1
            if n > 0:
                break
            p = len(self.buffer)
            yield
        r = self.buffer[:n]
        del self.buffer[:n]
        return r

    def readexactly(self, n):
        if n == 0:
            return b''
        while len(self.buffer) < n:
            yield
        r = self.buffer[:n]
        del self.buffer[:n]
        return r

    def feed_data(self, data):
        self.buffer += data

    def feed_eof(self):
        self.eof = True

    def at_eof(self):
        return self.eof and not self.buffer


def run_until_complete(test_coroutine):
    """
    Decorator that converts an async test coroutine to a sync test function.

    """

    @functools.wraps(test_coroutine)
    def test_function(self, *args, **kwds):
        self.loop.run_until_complete(test_coroutine(self, *args, **kwds))

    return test_function
