import functools
import inspect
import sys
import unittest

import trio.testing


if sys.version_info[:2] < (3, 11):  # pragma: no cover
    from exceptiongroup import BaseExceptionGroup


class IsolatedTrioTestCase(unittest.TestCase):
    """
    Wrap test coroutines with :func:`trio.testing.trio_test` automatically.

    Create a nursery for each test, available in the :attr:`nursery` attribute.

    :meth:`asyncSetUp` and :meth:`asyncTearDown` are supported, similar to
    :class:`unittest.IsolatedAsyncioTestCase`, but ``addAsyncCleanup`` isn't.

    """

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        for name in unittest.defaultTestLoader.getTestCaseNames(cls):
            test = getattr(cls, name)
            if getattr(test, "converted_to_trio", False):  # pragma: no cover
                return
            assert inspect.iscoroutinefunction(test)
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
            except BaseExceptionGroup as exc:  # pragma: no cover
                # Unwrap exceptions like unittest.SkipTest. Multiple exceptions
                # could occur is a test fails with multiple errors; this is OK;
                # raise the original exception group in that case.
                try:
                    trio._util.raise_single_exception_from_group(exc)
                except trio._util.MultipleExceptionError:  # pragma: no cover
                    raise exc

        new_test.converted_to_trio = True
        return new_test

    async def asyncSetUp(self):
        pass

    async def asyncTearDown(self):
        pass
