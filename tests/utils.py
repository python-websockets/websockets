import contextlib
import email.utils
import unittest
import warnings


DATE = email.utils.formatdate(usegmt=True)


class GeneratorTestCase(unittest.TestCase):
    """
    Base class for testing generator-based coroutines.

    """

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


class DeprecationTestCase(unittest.TestCase):
    """
    Base class for testing deprecations.

    """

    @contextlib.contextmanager
    def assertDeprecationWarning(self, message):
        """
        Check that a deprecation warning was raised with the given message.

        """
        with warnings.catch_warnings(record=True) as recorded_warnings:
            warnings.simplefilter("always")
            yield

        self.assertEqual(len(recorded_warnings), 1)
        warning = recorded_warnings[0]
        self.assertEqual(warning.category, DeprecationWarning)
        self.assertEqual(str(warning.message), message)
