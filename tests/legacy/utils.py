import asyncio
import functools
import sys
import unittest

from ..utils import AssertNoLogsMixin


class AsyncioTestCase(AssertNoLogsMixin, unittest.TestCase):
    """
    Base class for tests that sets up an isolated event loop for each test.

    IsolatedAsyncioTestCase was introduced in Python 3.8 for similar purposes
    but isn't a drop-in replacement.

    """

    def __init_subclass__(cls, **kwargs):
        """
        Convert test coroutines to test functions.

        This supports asynchronous tests transparently.

        """
        super().__init_subclass__(**kwargs)
        for name in unittest.defaultTestLoader.getTestCaseNames(cls):
            test = getattr(cls, name)
            if asyncio.iscoroutinefunction(test):
                setattr(cls, name, cls.convert_async_to_sync(test))

    @staticmethod
    def convert_async_to_sync(test):
        """
        Convert a test coroutine to a test function.

        """

        @functools.wraps(test)
        def test_func(self, *args, **kwargs):
            return self.loop.run_until_complete(test(self, *args, **kwargs))

        return test_func

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

    def assertDeprecationWarnings(self, recorded_warnings, expected_warnings):
        """
        Check recorded deprecation warnings match a list of expected messages.

        """
        # Work around https://github.com/python/cpython/issues/90476.
        if sys.version_info[:2] < (3, 11):  # pragma: no cover
            recorded_warnings = [
                recorded
                for recorded in recorded_warnings
                if not (
                    type(recorded.message) is ResourceWarning
                    and str(recorded.message).startswith("unclosed transport")
                )
            ]

        for recorded in recorded_warnings:
            self.assertIs(type(recorded.message), DeprecationWarning)
        self.assertEqual(
            {str(recorded.message) for recorded in recorded_warnings},
            set(expected_warnings),
        )
