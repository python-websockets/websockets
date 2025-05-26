import asyncio
import functools
import sys
import unittest

import trio.testing


if sys.version_info[:2] < (3, 11):  # pragma: no cover
    from exceptiongroup import ExceptionGroup


class IsolatedTrioTestCase(unittest.TestCase):
    """
    Wrap test coroutines with :func:`trio.testing.trio_test` automatically.

    Also initializes a nursery for each test and adds :meth:`asyncSetUp` and
    :meth:`asyncTearDown`, similar to :class:`unittest.IsolatedAsyncioTestCase`.

    """

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        for name in unittest.defaultTestLoader.getTestCaseNames(cls):
            test = getattr(cls, name)
            if getattr(test, "converted_to_trio", False):
                return
            assert asyncio.iscoroutinefunction(test)
            setattr(cls, name, cls.convert_to_trio(test))

    @staticmethod
    def convert_to_trio(test):
        @trio.testing.trio_test
        @functools.wraps(test)
        async def new_test(self, *args, **kwargs):
            try:
                # Provide a nursery so it's easy to start tasks.
                async with trio.open_nursery() as self.nursery:
                    await self.asyncSetUp()
                    try:
                        return await test(self, *args, **kwargs)
                    finally:
                        await self.asyncTearDown()
            except ExceptionGroup as exc_group:
                # Unwrap exceptions like unittest.SkipTest.
                if len(exc_group.exceptions) == 1:
                    raise exc_group.exceptions[0]
                else:  # pragma: no cover
                    raise

        new_test.converted_to_trio = True
        return new_test

    async def asyncSetUp(self):
        pass

    async def asyncTearDown(self):
        pass
