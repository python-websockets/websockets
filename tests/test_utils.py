import base64
import gc
import itertools
import logging
import platform
import socket
import unittest

from websockets.utils import (
    ConnectionLoggerAdapter,
    accept_key,
    apply_mask as py_apply_mask,
    generate_key,
    get_socket_name,
)

from .utils import temp_unix_socket_path


# Test vector from RFC 6455
KEY = "dGhlIHNhbXBsZSBub25jZQ=="
ACCEPT = "s3pPLMBiTxaQ9kYGzzhZRbK+xOo="


class UtilsTests(unittest.TestCase):
    def test_generate_key(self):
        key = generate_key()
        self.assertEqual(len(base64.b64decode(key.encode())), 16)

    def test_accept_key(self):
        self.assertEqual(accept_key(KEY), ACCEPT)


class ApplyMaskTests(unittest.TestCase):
    @staticmethod
    def apply_mask(*args, **kwargs):
        return py_apply_mask(*args, **kwargs)

    apply_mask_type_combos = list(itertools.product([bytes, bytearray], repeat=2))

    apply_mask_test_values = [
        (b"", b"1234", b""),
        (b"aBcDe", b"\x00\x00\x00\x00", b"aBcDe"),
        (b"abcdABCD", b"1234", b"PPPPpppp"),
        (b"abcdABCD" * 10, b"1234", b"PPPPpppp" * 10),
    ]

    def test_apply_mask(self):
        for data_type, mask_type in self.apply_mask_type_combos:
            for data_in, mask, data_out in self.apply_mask_test_values:
                data_in, mask = data_type(data_in), mask_type(mask)

                with self.subTest(data_in=data_in, mask=mask):
                    result = self.apply_mask(data_in, mask)
                    self.assertEqual(result, data_out)

    def test_apply_mask_memoryview(self):
        for mask_type in [bytes, bytearray]:
            for data_in, mask, data_out in self.apply_mask_test_values:
                data_in, mask = memoryview(data_in), mask_type(mask)

                with self.subTest(data_in=data_in, mask=mask):
                    result = self.apply_mask(data_in, mask)
                    self.assertEqual(result, data_out)

    def test_apply_mask_non_contiguous_memoryview(self):
        for mask_type in [bytes, bytearray]:
            for data_in, mask, data_out in self.apply_mask_test_values:
                data_in, mask = memoryview(data_in)[::-1], mask_type(mask)[::-1]
                data_out = data_out[::-1]

                with self.subTest(data_in=data_in, mask=mask):
                    result = self.apply_mask(data_in, mask)
                    self.assertEqual(result, data_out)

    def test_apply_mask_check_input_types(self):
        for data_in, mask in [(None, None), (b"abcd", None), (None, b"abcd")]:
            with self.subTest(data_in=data_in, mask=mask):
                with self.assertRaises(TypeError):
                    self.apply_mask(data_in, mask)

    def test_apply_mask_check_mask_length(self):
        for data_in, mask in [
            (b"", b""),
            (b"abcd", b"123"),
            (b"", b"aBcDe"),
            (b"12345678", b"12345678"),
        ]:
            with self.subTest(data_in=data_in, mask=mask):
                with self.assertRaises(ValueError):
                    self.apply_mask(data_in, mask)


try:
    from websockets.speedups import apply_mask as c_apply_mask
except ImportError:
    pass
else:

    class SpeedupsTests(ApplyMaskTests):
        @staticmethod
        def apply_mask(*args, **kwargs):
            try:
                return c_apply_mask(*args, **kwargs)
            except NotImplementedError as exc:  # pragma: no cover
                # PyPy doesn't implement creating contiguous readonly buffer
                # from non-contiguous. We don't care about this edge case.
                if (
                    platform.python_implementation() == "PyPy"
                    and "not implemented yet" in str(exc)
                ):
                    raise unittest.SkipTest(str(exc))
                else:
                    raise


class FakeConnection:
    """Object standing in for a connection; plain objects aren't weakrefable."""


class ConnectionLoggerAdapterTests(unittest.TestCase):
    def setUp(self):
        self.websocket = FakeConnection()
        self.adapter = ConnectionLoggerAdapter(
            logging.getLogger("websockets.test"),
            self.websocket,
        )

    def test_process_adds_websocket_to_extra(self):
        """process makes the connection available in the extra dict."""
        msg, kwargs = self.adapter.process("message", {})
        self.assertIs(kwargs["extra"]["websocket"], self.websocket)

    def test_log_records_have_websocket_attribute(self):
        """Log records have a websocket attribute referencing the connection."""
        with self.assertLogs("websockets.test", logging.INFO) as logs:
            self.adapter.info("message")
        self.assertIs(logs.records[0].websocket, self.websocket)

    def test_adapter_does_not_keep_websocket_alive(self):
        """Adapter doesn't prevent garbage collection of the connection."""
        del self.websocket
        gc.collect()
        msg, kwargs = self.adapter.process("message", {})
        self.assertNotIn("extra", kwargs)


class GetSocketNameAsStrTests(unittest.TestCase):
    def test_af_inet(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
            self.assertEqual(get_socket_name(sock), f"127.0.0.1:{port}")

    @unittest.skipUnless(socket.has_ipv6, "this test requires IPv6")
    def test_af_inet6(self):
        with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("::1", 0))
            except OSError:
                self.skipTest("IPv6 loopback isn't available")
            port = sock.getsockname()[1]
            self.assertEqual(get_socket_name(sock), f"[::1]:{port}")

    @unittest.skipUnless(hasattr(socket, "AF_UNIX"), "this test requires Unix sockets")
    def test_af_unix(self):
        with temp_unix_socket_path() as path:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.bind(path)
                self.assertEqual(get_socket_name(sock), path)
