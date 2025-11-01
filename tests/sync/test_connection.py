import contextlib
import itertools
import logging
import socket
import threading
import time
import uuid
from unittest.mock import Mock, patch

from websockets.exceptions import (
    ConcurrencyError,
    ConnectionClosedError,
    ConnectionClosedOK,
)
from websockets.frames import CloseCode, Frame, Opcode
from websockets.protocol import CLIENT, SERVER, Protocol, State
from websockets.sync.connection import *

from ..protocol import RecordingProtocol
from ..utils import MS
from .connection import InterceptingConnection
from .utils import ThreadTestCase


# Connection implements symmetrical behavior between clients and servers.
# All tests run on the client side and the server side to validate this.


class ClientConnectionTests(ThreadTestCase):
    LOCAL = CLIENT
    REMOTE = SERVER

    def setUp(self):
        socket_, remote_socket = socket.socketpair()
        protocol = Protocol(self.LOCAL)
        remote_protocol = RecordingProtocol(self.REMOTE)
        self.connection = Connection(socket_, protocol, close_timeout=2 * MS)
        self.remote_connection = InterceptingConnection(remote_socket, remote_protocol)

    def tearDown(self):
        self.remote_connection.close()
        self.connection.close()

    # Test helpers built upon RecordingProtocol and InterceptingConnection.

    def wait_for_remote_side(self):
        """Wait for the remote side to process messages."""
        # We don't have a way to tell if the remote side is blocked on I/O.
        # The sync tests still run faster than the asyncio and trio tests :-)
        time.sleep(MS)

    def assertFrameSent(self, frame):
        """Check that a single frame was sent."""
        self.wait_for_remote_side()
        self.assertEqual(self.remote_connection.protocol.get_frames_rcvd(), [frame])

    def assertNoFrameSent(self):
        """Check that no frame was sent."""
        self.wait_for_remote_side()
        self.assertEqual(self.remote_connection.protocol.get_frames_rcvd(), [])

    @contextlib.contextmanager
    def delay_frames_rcvd(self, delay):
        """Delay frames before they're received by the connection."""
        with self.remote_connection.delay_frames_sent(delay):
            yield
            self.wait_for_remote_side()

    @contextlib.contextmanager
    def delay_eof_rcvd(self, delay):
        """Delay EOF before it's received by the connection."""
        with self.remote_connection.delay_eof_sent(delay):
            yield
            self.wait_for_remote_side()

    @contextlib.contextmanager
    def drop_frames_rcvd(self):
        """Drop frames before they're received by the connection."""
        with self.remote_connection.drop_frames_sent():
            yield
            self.wait_for_remote_side()

    @contextlib.contextmanager
    def drop_eof_rcvd(self):
        """Drop EOF before it's received by the connection."""
        with self.remote_connection.drop_eof_sent():
            yield
            self.wait_for_remote_side()

    # Test __enter__ and __exit__.

    def test_enter(self):
        """__enter__ returns the connection itself."""
        with self.connection as connection:
            self.assertIs(connection, self.connection)

    def test_exit(self):
        """__exit__ closes the connection with code 1000."""
        with self.connection:
            self.assertNoFrameSent()
        self.assertFrameSent(Frame(Opcode.CLOSE, b"\x03\xe8"))

    def test_exit_with_exception(self):
        """__exit__ with an exception closes the connection with code 1011."""
        with self.assertRaises(RuntimeError):
            with self.connection:
                raise RuntimeError
        self.assertFrameSent(Frame(Opcode.CLOSE, b"\x03\xf3"))

    # Test __iter__.

    def test_iter_text(self):
        """__iter__ yields text messages."""
        iterator = iter(self.connection)
        with contextlib.closing(iterator):
            self.remote_connection.send("😀")
            self.assertEqual(next(iterator), "😀")
            self.remote_connection.send("😀")
            self.assertEqual(next(iterator), "😀")

    def test_iter_binary(self):
        """__iter__ yields binary messages."""
        iterator = iter(self.connection)
        with contextlib.closing(iterator):
            self.remote_connection.send(b"\x01\x02\xfe\xff")
            self.assertEqual(next(iterator), b"\x01\x02\xfe\xff")
            self.remote_connection.send(b"\x01\x02\xfe\xff")
            self.assertEqual(next(iterator), b"\x01\x02\xfe\xff")

    def test_iter_mixed(self):
        """__iter__ yields a mix of text and binary messages."""
        iterator = iter(self.connection)
        with contextlib.closing(iterator):
            self.remote_connection.send("😀")
            self.assertEqual(next(iterator), "😀")
            self.remote_connection.send(b"\x01\x02\xfe\xff")
            self.assertEqual(next(iterator), b"\x01\x02\xfe\xff")

    def test_iter_connection_closed_ok(self):
        """__iter__ terminates after a normal closure."""
        iterator = iter(self.connection)
        with contextlib.closing(iterator):
            self.remote_connection.close()
            with self.assertRaises(StopIteration):
                next(iterator)

    def test_iter_connection_closed_error(self):
        """__iter__ raises ConnectionClosedError after an error."""
        iterator = iter(self.connection)
        with contextlib.closing(iterator):
            self.remote_connection.close(code=CloseCode.INTERNAL_ERROR)
            with self.assertRaises(ConnectionClosedError):
                next(iterator)

    # Test recv.

    def test_recv_text(self):
        """recv receives a text message."""
        self.remote_connection.send("😀")
        self.assertEqual(self.connection.recv(), "😀")

    def test_recv_binary(self):
        """recv receives a binary message."""
        self.remote_connection.send(b"\x01\x02\xfe\xff")
        self.assertEqual(self.connection.recv(), b"\x01\x02\xfe\xff")

    def test_recv_text_as_bytes(self):
        """recv receives a text message as bytes."""
        self.remote_connection.send("😀")
        self.assertEqual(self.connection.recv(decode=False), "😀".encode())

    def test_recv_binary_as_text(self):
        """recv receives a binary message as a str."""
        self.remote_connection.send("😀".encode())
        self.assertEqual(self.connection.recv(decode=True), "😀")

    def test_recv_fragmented_text(self):
        """recv receives a fragmented text message."""
        self.remote_connection.send(["😀", "😀"])
        self.assertEqual(self.connection.recv(), "😀😀")

    def test_recv_fragmented_binary(self):
        """recv receives a fragmented binary message."""
        self.remote_connection.send([b"\x01\x02", b"\xfe\xff"])
        self.assertEqual(self.connection.recv(), b"\x01\x02\xfe\xff")

    def test_recv_connection_closed_ok(self):
        """recv raises ConnectionClosedOK after a normal closure."""
        self.remote_connection.close()
        with self.assertRaises(ConnectionClosedOK):
            self.connection.recv()

    def test_recv_connection_closed_error(self):
        """recv raises ConnectionClosedError after an error."""
        self.remote_connection.close(code=CloseCode.INTERNAL_ERROR)
        with self.assertRaises(ConnectionClosedError):
            self.connection.recv()

    def test_recv_non_utf8_text(self):
        """recv receives a non-UTF-8 text message."""
        self.remote_connection.send(b"\x01\x02\xfe\xff", text=True)
        with self.assertRaises(ConnectionClosedError):
            self.connection.recv()
        self.assertFrameSent(
            Frame(Opcode.CLOSE, b"\x03\xefinvalid start byte at position 2")
        )

    def test_recv_during_recv(self):
        """recv raises ConcurrencyError when called concurrently."""
        with self.run_in_thread(self.connection.recv):
            try:
                with self.assertRaises(ConcurrencyError) as raised:
                    self.connection.recv()
            finally:
                self.remote_connection.send("")
            self.assertEqual(
                str(raised.exception),
                "cannot call recv while another thread "
                "is already running recv or recv_streaming",
            )

    def test_recv_during_recv_streaming(self):
        """recv raises ConcurrencyError when called concurrently with recv_streaming."""
        with self.run_in_thread(lambda: list(self.connection.recv_streaming())):
            try:
                with self.assertRaises(ConcurrencyError) as raised:
                    self.connection.recv()
            finally:
                self.remote_connection.send("")
        self.assertEqual(
            str(raised.exception),
            "cannot call recv while another thread "
            "is already running recv or recv_streaming",
        )

    # Test recv_streaming.

    def test_recv_streaming_text(self):
        """recv_streaming receives a text message."""
        self.remote_connection.send("😀")
        self.assertEqual(
            list(self.connection.recv_streaming()),
            ["😀"],
        )

    def test_recv_streaming_binary(self):
        """recv_streaming receives a binary message."""
        self.remote_connection.send(b"\x01\x02\xfe\xff")
        self.assertEqual(
            list(self.connection.recv_streaming()),
            [b"\x01\x02\xfe\xff"],
        )

    def test_recv_streaming_text_as_bytes(self):
        """recv_streaming receives a text message as bytes."""
        self.remote_connection.send("😀")
        self.assertEqual(
            list(self.connection.recv_streaming(decode=False)),
            ["😀".encode()],
        )

    def test_recv_streaming_binary_as_str(self):
        """recv_streaming receives a binary message as a str."""
        self.remote_connection.send("😀".encode())
        self.assertEqual(
            list(self.connection.recv_streaming(decode=True)),
            ["😀"],
        )

    def test_recv_streaming_fragmented_text(self):
        """recv_streaming receives a fragmented text message."""
        self.remote_connection.send(["😀", "😀"])
        # websockets sends an trailing empty fragment. That's an implementation detail.
        self.assertEqual(
            list(self.connection.recv_streaming()),
            ["😀", "😀", ""],
        )

    def test_recv_streaming_fragmented_binary(self):
        """recv_streaming receives a fragmented binary message."""
        self.remote_connection.send([b"\x01\x02", b"\xfe\xff"])
        # websockets sends an trailing empty fragment. That's an implementation detail.
        self.assertEqual(
            list(self.connection.recv_streaming()),
            [b"\x01\x02", b"\xfe\xff", b""],
        )

    def test_recv_streaming_connection_closed_ok(self):
        """recv_streaming raises ConnectionClosedOK after a normal closure."""
        self.remote_connection.close()
        with self.assertRaises(ConnectionClosedOK):
            for _ in self.connection.recv_streaming():
                self.fail("did not raise")

    def test_recv_streaming_connection_closed_error(self):
        """recv_streaming raises ConnectionClosedError after an error."""
        self.remote_connection.close(code=CloseCode.INTERNAL_ERROR)
        with self.assertRaises(ConnectionClosedError):
            for _ in self.connection.recv_streaming():
                self.fail("did not raise")

    def test_recv_streaming_non_utf8_text(self):
        """recv_streaming receives a non-UTF-8 text message."""
        self.remote_connection.send(b"\x01\x02\xfe\xff", text=True)
        with self.assertRaises(ConnectionClosedError):
            list(self.connection.recv_streaming())
        self.assertFrameSent(
            Frame(Opcode.CLOSE, b"\x03\xefinvalid start byte at position 2")
        )

    def test_recv_streaming_during_recv(self):
        """recv_streaming raises ConcurrencyError when called concurrently with recv."""
        with self.run_in_thread(self.connection.recv):
            try:
                with self.assertRaises(ConcurrencyError) as raised:
                    for _ in self.connection.recv_streaming():
                        self.fail("did not raise")
            finally:
                self.remote_connection.send("")
        self.assertEqual(
            str(raised.exception),
            "cannot call recv_streaming while another thread "
            "is already running recv or recv_streaming",
        )

    def test_recv_streaming_during_recv_streaming(self):
        """recv_streaming raises ConcurrencyError when called concurrently."""
        with self.run_in_thread(lambda: list(self.connection.recv_streaming())):
            try:
                with self.assertRaises(ConcurrencyError) as raised:
                    for _ in self.connection.recv_streaming():
                        self.fail("did not raise")
            finally:
                self.remote_connection.send("")
        self.assertEqual(
            str(raised.exception),
            "cannot call recv_streaming while another thread "
            "is already running recv or recv_streaming",
        )

    # Test send.

    def test_send_text(self):
        """send sends a text message."""
        self.connection.send("😀")
        self.assertEqual(self.remote_connection.recv(), "😀")

    def test_send_binary(self):
        """send sends a binary message."""
        self.connection.send(b"\x01\x02\xfe\xff")
        self.assertEqual(self.remote_connection.recv(), b"\x01\x02\xfe\xff")

    def test_send_binary_from_str(self):
        """send sends a binary message from a str."""
        self.connection.send("😀", text=False)
        self.assertEqual(self.remote_connection.recv(), "😀".encode())

    def test_send_text_from_bytes(self):
        """send sends a text message from bytes."""
        self.connection.send("😀".encode(), text=True)
        self.assertEqual(self.remote_connection.recv(), "😀")

    def test_send_fragmented_text(self):
        """send sends a fragmented text message."""
        self.connection.send(["😀", "😀"])
        # websockets sends an trailing empty fragment. That's an implementation detail.
        self.assertEqual(
            list(self.remote_connection.recv_streaming()),
            ["😀", "😀", ""],
        )

    def test_send_fragmented_binary(self):
        """send sends a fragmented binary message."""
        self.connection.send([b"\x01\x02", b"\xfe\xff"])
        # websockets sends an trailing empty fragment. That's an implementation detail.
        self.assertEqual(
            list(self.remote_connection.recv_streaming()),
            [b"\x01\x02", b"\xfe\xff", b""],
        )

    def test_send_fragmented_binary_from_str(self):
        """send sends a fragmented binary message from a str."""
        self.connection.send(["😀", "😀"], text=False)
        # websockets sends an trailing empty fragment. That's an implementation detail.
        self.assertEqual(
            list(self.remote_connection.recv_streaming()),
            ["😀".encode(), "😀".encode(), b""],
        )

    def test_send_fragmented_text_from_bytes(self):
        """send sends a fragmented text message from bytes."""
        self.connection.send(["😀".encode(), "😀".encode()], text=True)
        # websockets sends an trailing empty fragment. That's an implementation detail.
        self.assertEqual(
            list(self.remote_connection.recv_streaming()),
            ["😀", "😀", ""],
        )

    def test_send_connection_closed_ok(self):
        """send raises ConnectionClosedOK after a normal closure."""
        self.remote_connection.close()
        with self.assertRaises(ConnectionClosedOK):
            self.connection.send("😀")

    def test_send_connection_closed_error(self):
        """send raises ConnectionClosedError after an error."""
        self.remote_connection.close(code=CloseCode.INTERNAL_ERROR)
        with self.assertRaises(ConnectionClosedError):
            self.connection.send("😀")

    def test_send_during_send(self):
        """send raises ConcurrencyError when called concurrently."""
        with self.run_in_thread(self.remote_connection.recv):
            send_gate = threading.Event()
            exit_gate = threading.Event()

            def fragments():
                yield "😀"
                send_gate.set()
                exit_gate.wait()
                yield "😀"

            send_thread = threading.Thread(
                target=self.connection.send,
                args=(fragments(),),
            )
            send_thread.start()

            send_gate.wait()
            # The check happens in four code paths, depending on the argument.
            for message in [
                "😀",
                b"\x01\x02\xfe\xff",
                ["😀", "😀"],
                [b"\x01\x02", b"\xfe\xff"],
            ]:
                with self.subTest(message=message):
                    with self.assertRaises(ConcurrencyError) as raised:
                        self.connection.send(message)
                    self.assertEqual(
                        str(raised.exception),
                        "cannot call send while another thread is already running send",
                    )

            exit_gate.set()
            send_thread.join()

    def test_send_empty_iterable(self):
        """send does nothing when called with an empty iterable."""
        self.connection.send([])
        self.connection.close()
        self.assertEqual(list(self.remote_connection), [])

    def test_send_mixed_iterable(self):
        """send raises TypeError when called with an iterable of inconsistent types."""
        with self.assertRaises(TypeError):
            self.connection.send(["😀", b"\xfe\xff"])

    def test_send_unsupported_iterable(self):
        """send raises TypeError when called with an iterable of unsupported type."""
        with self.assertRaises(TypeError):
            self.connection.send([None])

    def test_send_dict(self):
        """send raises TypeError when called with a dict."""
        with self.assertRaises(TypeError):
            self.connection.send({"type": "object"})

    def test_send_unsupported_type(self):
        """send raises TypeError when called with an unsupported type."""
        with self.assertRaises(TypeError):
            self.connection.send(None)

    # Test close.

    def test_close(self):
        """close sends a close frame."""
        self.connection.close()
        self.assertFrameSent(Frame(Opcode.CLOSE, b"\x03\xe8"))

    def test_close_explicit_code_reason(self):
        """close sends a close frame with a given code and reason."""
        self.connection.close(CloseCode.GOING_AWAY, "bye!")
        self.assertFrameSent(Frame(Opcode.CLOSE, b"\x03\xe9bye!"))

    def test_close_waits_for_close_frame(self):
        """close waits for a close frame then EOF before returning."""
        t0 = time.time()
        with self.delay_frames_rcvd(MS):
            self.connection.close()
        t1 = time.time()

        self.assertEqual(self.connection.state, State.CLOSED)
        self.assertEqual(self.connection.close_code, CloseCode.NORMAL_CLOSURE)
        self.assertGreater(t1 - t0, MS)

        with self.assertRaises(ConnectionClosedOK) as raised:
            self.connection.recv()

        exc = raised.exception
        self.assertEqual(str(exc), "sent 1000 (OK); then received 1000 (OK)")
        self.assertIsNone(exc.__cause__)

    def test_close_waits_for_connection_closed(self):
        """close waits for EOF before returning."""
        if self.LOCAL is SERVER:
            self.skipTest("only relevant on the client-side")

        t0 = time.time()
        with self.delay_eof_rcvd(MS):
            self.connection.close()
        t1 = time.time()

        self.assertEqual(self.connection.state, State.CLOSED)
        self.assertEqual(self.connection.close_code, CloseCode.NORMAL_CLOSURE)
        self.assertGreater(t1 - t0, MS)

        with self.assertRaises(ConnectionClosedOK) as raised:
            self.connection.recv()

        exc = raised.exception
        self.assertEqual(str(exc), "sent 1000 (OK); then received 1000 (OK)")
        self.assertIsNone(exc.__cause__)

    def test_close_timeout_waiting_for_close_frame(self):
        """close times out if no close frame is received."""
        t0 = time.time()
        with self.drop_frames_rcvd(), self.drop_eof_rcvd():
            self.connection.close()
        t1 = time.time()

        self.assertEqual(self.connection.state, State.CLOSED)
        self.assertEqual(self.connection.close_code, CloseCode.ABNORMAL_CLOSURE)
        self.assertGreater(t1 - t0, 2 * MS)

        with self.assertRaises(ConnectionClosedError) as raised:
            self.connection.recv()

        exc = raised.exception
        self.assertEqual(str(exc), "sent 1000 (OK); no close frame received")
        self.assertIsInstance(exc.__cause__, TimeoutError)

    def test_close_timeout_waiting_for_connection_closed(self):
        """close times out if EOF isn't received."""
        if self.LOCAL is SERVER:
            self.skipTest("only relevant on the client-side")

        t0 = time.time()
        with self.drop_eof_rcvd():
            self.connection.close()
        t1 = time.time()

        self.assertEqual(self.connection.state, State.CLOSED)
        self.assertEqual(self.connection.close_code, CloseCode.NORMAL_CLOSURE)
        self.assertGreater(t1 - t0, 2 * MS)

        with self.assertRaises(ConnectionClosedOK) as raised:
            self.connection.recv()

        exc = raised.exception
        self.assertEqual(str(exc), "sent 1000 (OK); then received 1000 (OK)")
        self.assertIsInstance(exc.__cause__, TimeoutError)

    def test_close_preserves_queued_messages(self):
        """close preserves messages buffered in the assembler."""
        self.remote_connection.send("😀")
        self.connection.close()

        self.assertEqual(self.connection.recv(), "😀")
        with self.assertRaises(ConnectionClosedOK):
            self.connection.recv()

    def test_close_idempotency(self):
        """close does nothing if the connection is already closed."""
        self.connection.close()
        self.assertFrameSent(Frame(Opcode.CLOSE, b"\x03\xe8"))

        self.connection.close()
        self.assertNoFrameSent()

    def test_close_idempotency_race_condition(self):
        """close waits if the connection is already closing."""

        self.connection.close_timeout = 6 * MS

        def closer():
            with self.delay_frames_rcvd(4 * MS):
                self.connection.close()

        with self.run_in_thread(closer):
            #  run_in_thread() waits for MS, which lets closer() send a close frame.
            self.assertFrameSent(Frame(Opcode.CLOSE, b"\x03\xe8"))

            # Connection isn't closed yet.
            with self.assertRaises(TimeoutError):
                self.connection.recv(timeout=MS)

            self.connection.close()
            self.assertNoFrameSent()

            # Connection is closed now.
            with self.assertRaises(ConnectionClosedOK):
                self.connection.recv(timeout=MS)

    def test_close_during_recv(self):
        """close aborts recv when called concurrently with recv."""
        with self.run_in_thread(self.connection.close):
            with self.assertRaises(ConnectionClosedOK) as raised:
                self.connection.recv()

        exc = raised.exception
        self.assertEqual(str(exc), "sent 1000 (OK); then received 1000 (OK)")
        self.assertIsNone(exc.__cause__)

    def test_close_during_send(self):
        """close fails the connection when called concurrently with send."""
        close_gate = threading.Event()
        exit_gate = threading.Event()

        def closer():
            close_gate.wait()
            self.connection.close()
            exit_gate.set()

        def fragments():
            yield "⏳"
            close_gate.set()
            exit_gate.wait()
            yield "⌛️"

        close_thread = threading.Thread(target=closer)
        close_thread.start()

        iterator = fragments()
        with contextlib.closing(iterator):
            with self.assertRaises(ConnectionClosedError) as raised:
                self.connection.send(iterator)

        exc = raised.exception
        self.assertEqual(
            str(exc),
            "sent 1011 (internal error) close during fragmented message; "
            "no close frame received",
        )
        self.assertIsNone(exc.__cause__)

        close_thread.join()

    # Test ping.

    @patch("random.getrandbits")
    def test_ping(self, getrandbits):
        """ping sends a ping frame with a random payload."""
        getrandbits.side_effect = itertools.count(1918987876)
        self.connection.ping()
        getrandbits.assert_called_once_with(32)
        self.assertFrameSent(Frame(Opcode.PING, b"rand"))

    def test_ping_explicit_text(self):
        """ping sends a ping frame with a payload provided as text."""
        self.connection.ping("ping")
        self.assertFrameSent(Frame(Opcode.PING, b"ping"))

    def test_ping_explicit_binary(self):
        """ping sends a ping frame with a payload provided as binary."""
        self.connection.ping(b"ping")
        self.assertFrameSent(Frame(Opcode.PING, b"ping"))

    def test_acknowledge_ping(self):
        """ping is acknowledged by a pong with the same payload."""
        with self.drop_frames_rcvd():  # drop automatic response to ping
            pong_received = self.connection.ping("this")
        self.remote_connection.pong("this")
        self.assertTrue(pong_received.wait(MS))

    def test_acknowledge_ping_non_matching_pong(self):
        """ping isn't acknowledged by a pong with a different payload."""
        with self.drop_frames_rcvd():  # drop automatic response to ping
            pong_received = self.connection.ping("this")
        self.remote_connection.pong("that")
        self.assertFalse(pong_received.wait(MS))

    def test_acknowledge_previous_ping(self):
        """ping is acknowledged by a pong for as a later ping."""
        with self.drop_frames_rcvd():  # drop automatic response to ping
            pong_received = self.connection.ping("this")
            self.connection.ping("that")
        self.remote_connection.pong("that")
        self.assertTrue(pong_received.wait(MS))

    def test_acknowledge_ping_on_close(self):
        """ping with ack_on_close is acknowledged when the connection is closed."""
        with self.drop_frames_rcvd():  # drop automatic response to ping
            pong_received_aoc = self.connection.ping("this", ack_on_close=True)
            pong_received = self.connection.ping("that")
        self.connection.close()
        self.assertTrue(pong_received_aoc.wait(MS))
        self.assertFalse(pong_received.wait(MS))

    def test_ping_duplicate_payload(self):
        """ping rejects the same payload until receiving the pong."""
        with self.drop_frames_rcvd():  # drop automatic response to ping
            pong_received = self.connection.ping("idem")

        with self.assertRaises(ConcurrencyError) as raised:
            self.connection.ping("idem")
        self.assertEqual(
            str(raised.exception),
            "already waiting for a pong with the same data",
        )

        self.remote_connection.pong("idem")
        self.assertTrue(pong_received.wait(MS))

        self.connection.ping("idem")  # doesn't raise an exception

    def test_ping_unsupported_type(self):
        """ping raises TypeError when called with an unsupported type."""
        with self.assertRaises(TypeError):
            self.connection.ping([])

    # Test pong.

    def test_pong(self):
        """pong sends a pong frame."""
        self.connection.pong()
        self.assertFrameSent(Frame(Opcode.PONG, b""))

    def test_pong_explicit_text(self):
        """pong sends a pong frame with a payload provided as text."""
        self.connection.pong("pong")
        self.assertFrameSent(Frame(Opcode.PONG, b"pong"))

    def test_pong_explicit_binary(self):
        """pong sends a pong frame with a payload provided as binary."""
        self.connection.pong(b"pong")
        self.assertFrameSent(Frame(Opcode.PONG, b"pong"))

    def test_pong_unsupported_type(self):
        """pong raises TypeError when called with an unsupported type."""
        with self.assertRaises(TypeError):
            self.connection.pong([])

    # Test keepalive.

    @patch("random.getrandbits")
    def test_keepalive(self, getrandbits):
        """keepalive sends pings at ping_interval and measures latency."""
        getrandbits.side_effect = itertools.count(1918987876)
        self.connection.ping_interval = 4 * MS
        self.connection.start_keepalive()
        self.assertIsNotNone(self.connection.keepalive_thread)
        self.assertEqual(self.connection.latency, 0)
        # 3 ms: keepalive() sends a ping frame.
        # 3.x ms: a pong frame is received.
        time.sleep(4 * MS)
        # 4 ms: check that the ping frame was sent.
        self.assertFrameSent(Frame(Opcode.PING, b"rand"))
        self.assertGreater(self.connection.latency, 0)
        self.assertLess(self.connection.latency, MS)

    def test_disable_keepalive(self):
        """keepalive is disabled when ping_interval is None."""
        self.connection.ping_interval = None
        self.connection.start_keepalive()
        self.assertIsNone(self.connection.keepalive_thread)

    @patch("random.getrandbits")
    def test_keepalive_times_out(self, getrandbits):
        """keepalive closes the connection if ping_timeout elapses."""
        getrandbits.side_effect = itertools.count(1918987876)
        self.connection.ping_interval = 4 * MS
        self.connection.ping_timeout = 2 * MS
        with self.drop_frames_rcvd():
            self.connection.start_keepalive()
            # 4 ms: keepalive() sends a ping frame.
            # 4.x ms: a pong frame is dropped.
            time.sleep(4 * MS)
            # Exiting the context manager sleeps for 1 ms.
        # 6 ms: no pong frame is received; the connection is closed.
        time.sleep(2 * MS)
        # 7 ms: check that the connection is closed.
        self.assertEqual(self.connection.state, State.CLOSED)

    @patch("random.getrandbits")
    def test_keepalive_ignores_timeout(self, getrandbits):
        """keepalive ignores timeouts if ping_timeout isn't set."""
        getrandbits.side_effect = itertools.count(1918987876)
        self.connection.ping_interval = 4 * MS
        self.connection.ping_timeout = None
        with self.drop_frames_rcvd():
            self.connection.start_keepalive()
            # 4 ms: keepalive() sends a ping frame.
            time.sleep(4 * MS)
            # Exiting the context manager sleeps for 1 ms.
            # 4.x ms: a pong frame is dropped.
        # 6 ms: no pong frame is received; the connection remains open.
        time.sleep(2 * MS)
        # 7 ms: check that the connection is still open.
        self.assertEqual(self.connection.state, State.OPEN)

    def test_keepalive_terminates_while_sleeping(self):
        """keepalive task terminates while waiting to send a ping."""
        self.connection.ping_interval = 3 * MS
        self.connection.start_keepalive()
        self.assertTrue(self.connection.keepalive_thread.is_alive())
        time.sleep(MS)
        self.assertTrue(self.connection.keepalive_thread.is_alive())
        self.connection.close()
        self.connection.keepalive_thread.join(MS)
        self.assertFalse(self.connection.keepalive_thread.is_alive())

    def test_keepalive_terminates_when_sending_ping_fails(self):
        """keepalive task terminates when sending a ping fails."""
        self.connection.ping_interval = MS
        self.connection.start_keepalive()
        self.assertTrue(self.connection.keepalive_thread.is_alive())
        with self.drop_eof_rcvd(), self.drop_frames_rcvd():
            self.connection.close()
            # Exiting the context managers sleeps for 2 ms.
        self.assertFalse(self.connection.keepalive_thread.is_alive())

    def test_keepalive_terminates_while_waiting_for_pong(self):
        """keepalive task terminates while waiting to receive a pong."""
        self.connection.ping_interval = MS
        self.connection.ping_timeout = 4 * MS
        with self.drop_frames_rcvd():
            self.connection.start_keepalive()
            # 1 ms: keepalive() sends a ping frame.
            # 1.x ms: a pong frame is dropped.
            time.sleep(MS)
            # Exiting the context manager sleeps for 1 ms.
        # 2 ms: close the connection before ping_timeout elapses.
        self.connection.close()
        self.connection.keepalive_thread.join(MS)
        self.assertFalse(self.connection.keepalive_thread.is_alive())

    def test_keepalive_reports_errors(self):
        """keepalive reports unexpected errors in logs."""
        self.connection.ping_interval = 2 * MS
        self.connection.start_keepalive()
        # Inject a fault when waiting to receive a pong.
        with self.assertLogs("websockets", logging.ERROR) as logs:
            with patch("threading.Event.wait", side_effect=Exception("BOOM")):
                # 2 ms: keepalive() sends a ping frame.
                # 2.x ms: a pong frame is dropped.
                time.sleep(3 * MS)
        self.assertEqual(
            [record.getMessage() for record in logs.records],
            ["keepalive ping failed"],
        )
        self.assertEqual(
            [str(record.exc_info[1]) for record in logs.records],
            ["BOOM"],
        )

    # Test parameters.

    def test_close_timeout(self):
        """close_timeout parameter configures close timeout."""
        connection = Connection(
            Mock(spec=socket.socket),
            Protocol(self.LOCAL),
            close_timeout=42 * MS,
        )
        self.assertEqual(connection.close_timeout, 42 * MS)

    def test_max_queue(self):
        """max_queue configures high-water mark of frames buffer."""
        connection = Connection(
            Mock(spec=socket.socket),
            Protocol(self.LOCAL),
            max_queue=4,
        )
        self.assertEqual(connection.recv_messages.high, 4)

    def test_max_queue_none(self):
        """max_queue disables high-water mark of frames buffer."""
        connection = Connection(
            Mock(spec=socket.socket),
            Protocol(self.LOCAL),
            max_queue=None,
        )
        self.assertEqual(connection.recv_messages.high, None)
        self.assertEqual(connection.recv_messages.high, None)

    def test_max_queue_tuple(self):
        """max_queue configures high-water and low-water marks of frames buffer."""
        connection = Connection(
            Mock(spec=socket.socket),
            Protocol(self.LOCAL),
            max_queue=(4, 2),
        )
        self.assertEqual(connection.recv_messages.high, 4)
        self.assertEqual(connection.recv_messages.low, 2)

    # Test attributes.

    def test_id(self):
        """Connection has an id attribute."""
        self.assertIsInstance(self.connection.id, uuid.UUID)

    def test_logger(self):
        """Connection has a logger attribute."""
        self.assertIsInstance(self.connection.logger, logging.LoggerAdapter)

    @patch("socket.socket.getsockname", return_value=("sock", 1234))
    def test_local_address(self, getsockname):
        """Connection provides a local_address attribute."""
        self.assertEqual(self.connection.local_address, ("sock", 1234))
        getsockname.assert_called_with()

    @patch("socket.socket.getpeername", return_value=("peer", 1234))
    def test_remote_address(self, getpeername):
        """Connection provides a remote_address attribute."""
        self.assertEqual(self.connection.remote_address, ("peer", 1234))
        getpeername.assert_called_with()

    def test_state(self):
        """Connection has a state attribute."""
        self.assertIs(self.connection.state, State.OPEN)

    def test_request(self):
        """Connection has a request attribute."""
        self.assertIsNone(self.connection.request)

    def test_response(self):
        """Connection has a response attribute."""
        self.assertIsNone(self.connection.response)

    def test_subprotocol(self):
        """Connection has a subprotocol attribute."""
        self.assertIsNone(self.connection.subprotocol)

    def test_close_code(self):
        """Connection has a close_code attribute."""
        self.assertIsNone(self.connection.close_code)

    def test_close_reason(self):
        """Connection has a close_reason attribute."""
        self.assertIsNone(self.connection.close_reason)

    # Test reporting of network errors.

    def test_writing_in_recv_events_fails(self):
        """Error when responding to incoming frames is correctly reported."""
        # Inject a fault by shutting down the socket for writing — but not by
        # closing it because that would terminate the connection.
        self.connection.socket.shutdown(socket.SHUT_WR)
        # Receive a ping. Responding with a pong will fail.
        self.remote_connection.ping()
        # The connection closed exception reports the injected fault.
        with self.assertRaises(ConnectionClosedError) as raised:
            self.connection.recv()
        self.assertIsInstance(raised.exception.__cause__, BrokenPipeError)

    def test_writing_in_send_context_fails(self):
        """Error when sending outgoing frame is correctly reported."""
        # Inject a fault by shutting down the socket for writing — but not by
        # closing it because that would terminate the connection.
        self.connection.socket.shutdown(socket.SHUT_WR)
        # Sending a pong will fail.
        # The connection closed exception reports the injected fault.
        with self.assertRaises(ConnectionClosedError) as raised:
            self.connection.pong()
        self.assertIsInstance(raised.exception.__cause__, BrokenPipeError)

    # Test safety nets — catching all exceptions in case of bugs.

    @patch("websockets.protocol.Protocol.events_received", side_effect=AssertionError)
    def test_unexpected_failure_in_recv_events(self, events_received):
        """Unexpected internal error in recv_events() is correctly reported."""
        self.remote_connection.send("😀")
        with self.assertRaises(ConnectionClosedError) as raised:
            self.connection.recv()
        self.assertIsInstance(raised.exception.__cause__, AssertionError)

    @patch("websockets.protocol.Protocol.send_text", side_effect=AssertionError)
    def test_unexpected_failure_in_send_context(self, send_text):
        """Unexpected internal error in send_context() is correctly reported."""
        # Send a message to trigger the fault.
        # The connection closed exception reports the injected fault.
        with self.assertRaises(ConnectionClosedError) as raised:
            self.connection.send("😀")
        self.assertIsInstance(raised.exception.__cause__, AssertionError)


class ServerConnectionTests(ClientConnectionTests):
    LOCAL = SERVER
    REMOTE = CLIENT
