import asyncio
import functools
import unittest

import trio.testing


class IsolatedTrioTestCase(unittest.TestCase):
    """
    Wrap test coroutines with :func:`trio.testing.trio_test` automatically.

    """

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        for name in unittest.defaultTestLoader.getTestCaseNames(cls):
            test = getattr(cls, name)
            assert asyncio.iscoroutinefunction(test)
            setattr(cls, name, cls.convert_to_trio(test))

    @staticmethod
    def convert_to_trio(test):
        @trio.testing.trio_test
        @functools.wraps(test)
        async def new_test(self, *args, **kwargs):
            return await test(self, *args, **kwargs)

        return new_test
