import contextlib
import email.utils
import logging
import os
import pathlib
import platform
import ssl
import sys
import tempfile
import time
import unittest
import warnings

from websockets.version import released


# Generate TLS certificate with:
# $ openssl req -x509 -config test_localhost.cnf -days 15340 -newkey rsa:2048 \
#       -out test_localhost.crt -keyout test_localhost.key
# $ cat test_localhost.key test_localhost.crt > test_localhost.pem
# $ rm test_localhost.key test_localhost.crt

CERTIFICATE = bytes(pathlib.Path(__file__).with_name("test_localhost.pem"))

CLIENT_CONTEXT = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
CLIENT_CONTEXT.load_verify_locations(CERTIFICATE)


SERVER_CONTEXT = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
SERVER_CONTEXT.load_cert_chain(CERTIFICATE)

# Work around https://github.com/openssl/openssl/issues/7967

# This bug causes connect() to hang in tests for the client. Including this
# workaround acknowledges that the issue could happen outside of the test suite.

# It shouldn't happen too often, or else OpenSSL 1.1.1 would be unusable. If it
# happens, we can look for a library-level fix, but it won't be easy.

SERVER_CONTEXT.num_tickets = 0


DATE = email.utils.formatdate(usegmt=True)


# Unit for timeouts. May be increased in slow or noisy environments by setting
# the WEBSOCKETS_TESTS_TIMEOUT_FACTOR environment variable.

# Downstream distributors insist on running the test suite despites my pleas to
# the contrary. They do it on build farms with unstable performance, leading to
# flakiness, and then they file bugs. Make tests 100x slower to avoid flakiness.

MS = 0.001 * float(
    os.environ.get(
        "WEBSOCKETS_TESTS_TIMEOUT_FACTOR",
        "100" if released else "1",
    )
)

# PyPy, asyncio's debug mode, and coverage penalize performance of this
# test suite. Increase timeouts to reduce the risk of spurious failures.
if platform.python_implementation() == "PyPy":  # pragma: no cover
    MS *= 2
if os.environ.get("PYTHONASYNCIODEBUG"):  # pragma: no cover
    MS *= 2
if os.environ.get("COVERAGE_RUN"):  # pragma: no branch
    MS *= 2

# Ensure that timeouts are larger than the clock's resolution (for Windows).
MS = max(MS, 2.5 * time.get_clock_info("monotonic").resolution)


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


class AssertNoLogsMixin:
    """
    Backport of assertNoLogs for Python 3.9.

    """

    if sys.version_info[:2] < (3, 10):  # pragma: no cover

        @contextlib.contextmanager
        def assertNoLogs(self, logger=None, level=None):
            """
            No message is logged on the given logger with at least the given level.

            """
            with self.assertLogs(logger, level) as logs:
                # We want to test that no log message is emitted
                # but assertLogs expects at least one log message.
                logging.getLogger(logger).log(level, "dummy")
                yield

            level_name = logging.getLevelName(level)
            self.assertEqual(logs.output, [f"{level_name}:{logger}:dummy"])


@contextlib.contextmanager
def temp_unix_socket_path():
    with tempfile.TemporaryDirectory() as temp_dir:
        yield str(pathlib.Path(temp_dir) / "websockets")
