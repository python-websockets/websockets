import asyncio
import contextlib
import functools
import os
import time
import unittest
import unittest.mock

from .compatibility import asyncio_ensure_future
from .exceptions import InvalidState
from .framing import *
from .protocol import CLOSED, WebSocketCommonProtocol


# Unit for timeouts. May be increased on slow machines by setting the
# WEBSOCKETS_TESTS_TIMEOUT_FACTOR environment variables.
MS = 0.001 * int(os.environ.get('WEBSOCKETS_TESTS_TIMEOUT_FACTOR', 1))

# asyncio's debug mode has a 10x performance penalty for this test suite.
if os.environ.get('PYTHONASYNCIODEBUG'):                    # pragma: no cover
    MS *= 10

# Ensure that timeouts are larger than the clock's resolution (for Windows).
MS = max(MS, 2.5 * time.get_clock_info('monotonic').resolution)


class TransportMock(unittest.mock.Mock):
    """
    Transport mock to control the protocol's inputs and outputs in tests.

    It calls the protocol's connection_made and connection_lost methods like
    actual transports.

    To simulate incoming data, tests call the protocol's data_received and
    eof_received methods directly.

    They could also pause_writing and resume_writing to test flow control.
    """
    # This should happen in __init__ but overriding Mock.__init__ is hard.
    def connect(self, loop, protocol):
        self.loop = loop
        self.protocol = protocol
        self.loop.call_soon(self.protocol.connection_made, self)

    def close(self):
        self.loop.call_soon(self.protocol.connection_lost, None)


class CommonTests:

    def setUp(self):
        super().setUp()
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.protocol = WebSocketCommonProtocol()
        self.transport = TransportMock()
        self.transport.connect(self.loop, self.protocol)

    def tearDown(self):
        self.loop.run_until_complete(
            self.protocol.close_connection(force=True))
        self.loop.close()
        super().tearDown()

    def run_loop_once(self):
        # Process callbacks scheduled with call_soon by appending a callback
        # to stop the event loop then running it until it hits that callback.
        self.loop.call_soon(self.loop.stop)
        self.loop.run_forever()

    def make_drain_slow(self):
        # Process connection_made in order to initialize self.protocol.writer.
        self.run_loop_once()

        original_drain = self.protocol.writer.drain

        @asyncio.coroutine
        def delayed_drain():
            yield from asyncio.sleep(3 * MS, loop=self.loop)
            yield from original_drain()

        self.protocol.writer.drain = delayed_drain

    # These frames are used in the ServerTests and ClientTests subclasses.
    close_frame = Frame(True, OP_CLOSE, serialize_close(1000, 'close'))
    client_close = Frame(True, OP_CLOSE, serialize_close(1000, 'client'))
    server_close = Frame(True, OP_CLOSE, serialize_close(1000, 'server'))

    @property
    def async(self):
        return functools.partial(asyncio_ensure_future, loop=self.loop)

    def receive_frame(self, frame):
        """
        Make the protocol receive a frame.
        """
        writer = self.protocol.data_received
        mask = not self.protocol.is_client
        self.loop.call_soon(write_frame, frame, writer, mask)

    def receive_eof(self):
        """
        Make the protocol receive the end of stream.

        WebSocketCommonProtocol.eof_received returns None — it is inherited
        from StreamReaderProtocol. (Returning True wouldn't work on secure
        connections anyway.) As a consequence, actual transports close
        themselves after calling it.

        To emulate this behavior, tests must close the transport just after
        calling the protocol's eof_received. Closing the transport will have
        the side-effect calling the protocol's connection_lost.

        This method is often called shortly after simulating invalid data to
        ensure that the connection fails quickly.
        """
        self.loop.call_soon(self.protocol.eof_received)
        self.loop.call_soon(self.transport.close)

    def process_control_frames(self):
        """
        Process control frames received by the protocol.

        To ensure that recv completes quickly, receive an additional dummy
        frame, which recv() will drop.
        """
        self.receive_frame(Frame(True, OP_TEXT, b''))
        self.loop.run_until_complete(self.protocol.recv())

    def last_sent_frame(self):
        """
        Read the last frame sent to the transport.

        This method assumes that at most one frame was sent. It raises an
        AssertionError otherwise.
        """
        stream = asyncio.StreamReader(loop=self.loop)

        for (data,), kw in self.transport.write.call_args_list:
            stream.feed_data(data)
        self.transport.write.call_args_list = []
        stream.feed_eof()

        if stream.at_eof():
            frame = None
        else:
            frame = self.loop.run_until_complete(read_frame(
                stream.readexactly, self.protocol.is_client))

        if not stream.at_eof():                             # pragma: no cover
            data = self.loop.run_until_complete(stream.read())
            raise AssertionError("Trailing data found: {!r}".format(data))

        return frame

    def assertOneFrameSent(self, fin, opcode, data):
        self.assertEqual(self.last_sent_frame(), Frame(fin, opcode, data))

    def assertNoFrameSent(self):
        self.assertIsNone(self.last_sent_frame())

    def assertConnectionClosed(self, code, message):
        # The following line guarantees that connection_lost was called.
        self.assertEqual(self.protocol.state, CLOSED)
        self.assertEqual(self.protocol.close_code, code)
        self.assertEqual(self.protocol.close_reason, message)

    @contextlib.contextmanager
    def assertCompletesWithin(self, min_time, max_time):
        t0 = self.loop.time()
        yield
        t1 = self.loop.time()
        dt = t1 - t0
        self.assertGreaterEqual(
            dt, min_time, "Too fast: {} < {}".format(dt, min_time))
        self.assertLess(
            dt, max_time, "Too slow: {} >= {}".format(dt, max_time))

    def test_local_address(self):
        get_extra_info = unittest.mock.Mock(return_value=('host', 4312))
        self.transport.get_extra_info = get_extra_info
        # The connection isn't established yet.
        self.assertEqual(self.protocol.local_address, None)
        self.run_loop_once()
        # The connection is established.
        self.assertEqual(self.protocol.local_address, ('host', 4312))
        get_extra_info.assert_called_once_with('sockname', None)

    def test_remote_address(self):
        get_extra_info = unittest.mock.Mock(return_value=('host', 4312))
        self.transport.get_extra_info = get_extra_info
        # The connection isn't established yet.
        self.assertEqual(self.protocol.remote_address, None)
        self.run_loop_once()
        # The connection is established.
        self.assertEqual(self.protocol.remote_address, ('host', 4312))
        get_extra_info.assert_called_once_with('peername', None)

    def test_open(self):
        self.assertTrue(self.protocol.open)
        self.protocol.connection_lost(None)
        self.assertFalse(self.protocol.open)

    def test_connection_lost(self):
        self.protocol.connection_lost(None)
        self.assertConnectionClosed(1006, '')

    def test_recv_text(self):
        self.receive_frame(Frame(True, OP_TEXT, 'café'.encode('utf-8')))
        data = self.loop.run_until_complete(self.protocol.recv())
        self.assertEqual(data, 'café')

    def test_recv_binary(self):
        self.receive_frame(Frame(True, OP_BINARY, b'tea'))
        data = self.loop.run_until_complete(self.protocol.recv())
        self.assertEqual(data, b'tea')

    def test_recv_protocol_error(self):
        self.receive_frame(Frame(True, OP_CONT, 'café'.encode('utf-8')))
        self.receive_eof()
        self.assertIsNone(self.loop.run_until_complete(self.protocol.recv()))
        self.assertConnectionClosed(1002, '')

    def test_recv_unicode_error(self):
        self.receive_frame(Frame(True, OP_TEXT, 'café'.encode('latin-1')))
        self.receive_eof()
        self.assertIsNone(self.loop.run_until_complete(self.protocol.recv()))
        self.assertConnectionClosed(1007, '')

    def test_recv_text_payload_too_big(self):
        self.protocol.max_size = 1024
        self.receive_frame(Frame(True, OP_TEXT, 'café'.encode('utf-8') * 205))
        self.receive_eof()
        self.assertIsNone(self.loop.run_until_complete(self.protocol.recv()))
        self.assertConnectionClosed(1009, '')

    def test_recv_binary_payload_too_big(self):
        self.protocol.max_size = 1024
        self.receive_frame(Frame(True, OP_BINARY, b'tea' * 342))
        self.receive_eof()
        self.assertIsNone(self.loop.run_until_complete(self.protocol.recv()))
        self.assertConnectionClosed(1009, '')

    def test_recv_text_no_max_size(self):
        self.protocol.max_size = None       # for test coverage
        self.receive_frame(Frame(True, OP_TEXT, 'café'.encode('utf-8') * 205))
        data = self.loop.run_until_complete(self.protocol.recv())
        self.assertEqual(data, 'café' * 205)

    def test_recv_binary_no_max_size(self):
        self.protocol.max_size = None       # for test coverage
        self.receive_frame(Frame(True, OP_BINARY, b'tea' * 342))
        data = self.loop.run_until_complete(self.protocol.recv())
        self.assertEqual(data, b'tea' * 342)

    def test_recv_other_error(self):
        @asyncio.coroutine
        def read_message():
            raise Exception("BOOM")
        self.protocol.read_message = read_message
        self.receive_eof()
        self.assertIsNone(self.loop.run_until_complete(self.protocol.recv()))
        with self.assertRaises(Exception):
            self.loop.run_until_complete(self.protocol.worker)
        self.assertConnectionClosed(1011, '')

    def test_recv_on_closed_connection(self):
        self.receive_eof()
        self.assertIsNone(self.loop.run_until_complete(self.protocol.recv()))

    def test_recv_cancelled(self):
        recv = self.async(self.protocol.recv())
        self.loop.call_soon(recv.cancel)
        with self.assertRaises(asyncio.CancelledError):
            self.loop.run_until_complete(recv)

        # The next frame doesn't disappear in a vacuum (it used to).
        self.receive_frame(Frame(True, OP_TEXT, 'café'.encode('utf-8')))
        data = self.loop.run_until_complete(self.protocol.recv())
        self.assertEqual(data, 'café')

    def test_send_text(self):
        self.loop.run_until_complete(self.protocol.send('café'))
        self.assertOneFrameSent(True, OP_TEXT, 'café'.encode('utf-8'))

    def test_send_binary(self):
        self.loop.run_until_complete(self.protocol.send(b'tea'))
        self.assertOneFrameSent(True, OP_BINARY, b'tea')

    def test_send_type_error(self):
        with self.assertRaises(TypeError):
            self.loop.run_until_complete(self.protocol.send(42))
        self.assertNoFrameSent()

    def test_send_on_closed_connection(self):
        self.receive_eof()
        # Ensure the protocol processes the connection termination.
        self.loop.run_until_complete(self.protocol.recv())
        with self.assertRaises(InvalidState):
            self.loop.run_until_complete(self.protocol.send('foobar'))
        self.assertNoFrameSent()

    def test_answer_ping(self):
        self.receive_frame(Frame(True, OP_PING, b'test'))
        self.process_control_frames()
        self.assertOneFrameSent(True, OP_PONG, b'test')

    def test_ignore_pong(self):
        self.receive_frame(Frame(True, OP_PONG, b'test'))
        self.process_control_frames()
        self.assertNoFrameSent()

    def test_acknowledge_ping(self):
        ping = self.loop.run_until_complete(self.protocol.ping())
        self.assertFalse(ping.done())
        ping_frame = self.last_sent_frame()
        pong_frame = Frame(True, OP_PONG, ping_frame.data)
        self.receive_frame(pong_frame)
        self.process_control_frames()
        self.assertTrue(ping.done())

    def test_acknowledge_previous_pings(self):
        pings = [(
            self.loop.run_until_complete(self.protocol.ping()),
            self.last_sent_frame(),
        ) for i in range(3)]
        # Unsolicited pong doesn't acknowledge pings
        self.receive_frame(Frame(True, OP_PONG, b''))
        self.process_control_frames()
        self.assertFalse(pings[0][0].done())
        self.assertFalse(pings[1][0].done())
        self.assertFalse(pings[2][0].done())
        # Pong acknowledges all previous pings
        self.receive_frame(Frame(True, OP_PONG, pings[1][1].data))
        self.process_control_frames()
        self.assertTrue(pings[0][0].done())
        self.assertTrue(pings[1][0].done())
        self.assertFalse(pings[2][0].done())

    def test_cancel_ping(self):
        ping = self.loop.run_until_complete(self.protocol.ping())
        ping_frame = self.last_sent_frame()
        ping.cancel()
        pong_frame = Frame(True, OP_PONG, ping_frame.data)
        self.receive_frame(pong_frame)
        self.process_control_frames()
        self.assertTrue(ping.cancelled())

    def test_duplicate_ping(self):
        self.loop.run_until_complete(self.protocol.ping(b'foobar'))
        self.assertOneFrameSent(True, OP_PING, b'foobar')
        with self.assertRaises(ValueError):
            self.loop.run_until_complete(self.protocol.ping(b'foobar'))
        self.assertNoFrameSent()

    def test_fragmented_text(self):
        self.receive_frame(Frame(False, OP_TEXT, 'ca'.encode('utf-8')))
        self.receive_frame(Frame(True, OP_CONT, 'fé'.encode('utf-8')))
        data = self.loop.run_until_complete(self.protocol.recv())
        self.assertEqual(data, 'café')

    def test_fragmented_binary(self):
        self.receive_frame(Frame(False, OP_BINARY, b't'))
        self.receive_frame(Frame(False, OP_CONT, b'e'))
        self.receive_frame(Frame(True, OP_CONT, b'a'))
        data = self.loop.run_until_complete(self.protocol.recv())
        self.assertEqual(data, b'tea')

    def test_fragmented_text_payload_too_big(self):
        self.protocol.max_size = 1024
        self.receive_frame(Frame(False, OP_TEXT, 'café'.encode('utf-8') * 100))
        self.receive_frame(Frame(True, OP_CONT, 'café'.encode('utf-8') * 105))
        self.receive_eof()
        self.assertIsNone(self.loop.run_until_complete(self.protocol.recv()))
        self.assertConnectionClosed(1009, '')

    def test_fragmented_binary_payload_too_big(self):
        self.protocol.max_size = 1024
        self.receive_frame(Frame(False, OP_BINARY, b'tea' * 171))
        self.receive_frame(Frame(True, OP_CONT, b'tea' * 171))
        self.receive_eof()
        self.assertIsNone(self.loop.run_until_complete(self.protocol.recv()))
        self.assertConnectionClosed(1009, '')

    def test_fragmented_text_no_max_size(self):
        self.protocol.max_size = None       # for test coverage
        self.receive_frame(Frame(False, OP_TEXT, 'café'.encode('utf-8') * 100))
        self.receive_frame(Frame(True, OP_CONT, 'café'.encode('utf-8') * 105))
        data = self.loop.run_until_complete(self.protocol.recv())
        self.assertEqual(data, 'café' * 205)

    def test_fragmented_binary_no_max_size(self):
        self.protocol.max_size = None       # for test coverage
        self.receive_frame(Frame(False, OP_BINARY, b'tea' * 171))
        self.receive_frame(Frame(True, OP_CONT, b'tea' * 171))
        data = self.loop.run_until_complete(self.protocol.recv())
        self.assertEqual(data, b'tea' * 342)

    def test_control_frame_within_fragmented_text(self):
        self.receive_frame(Frame(False, OP_TEXT, 'ca'.encode('utf-8')))
        self.receive_frame(Frame(True, OP_PING, b''))
        self.receive_frame(Frame(True, OP_CONT, 'fé'.encode('utf-8')))
        data = self.loop.run_until_complete(self.protocol.recv())
        self.assertEqual(data, 'café')
        self.assertOneFrameSent(True, OP_PONG, b'')

    def test_unterminated_fragmented_text(self):
        self.receive_frame(Frame(False, OP_TEXT, 'ca'.encode('utf-8')))
        # Missing the second part of the fragmented frame.
        self.receive_frame(Frame(True, OP_BINARY, b'tea'))
        self.receive_eof()
        self.assertIsNone(self.loop.run_until_complete(self.protocol.recv()))
        self.assertConnectionClosed(1002, '')

    def test_close_handshake_in_fragmented_text(self):
        self.receive_frame(Frame(False, OP_TEXT, 'ca'.encode('utf-8')))
        self.receive_frame(Frame(True, OP_CLOSE, b''))
        self.receive_eof()
        self.assertIsNone(self.loop.run_until_complete(self.protocol.recv()))
        self.assertConnectionClosed(1005, '')

    def test_connection_close_in_fragmented_text(self):
        self.receive_frame(Frame(False, OP_TEXT, 'ca'.encode('utf-8')))
        self.receive_eof()
        self.assertIsNone(self.loop.run_until_complete(self.protocol.recv()))
        self.assertConnectionClosed(1006, '')


class ServerCloseTests(CommonTests, unittest.TestCase):

    def test_server_close(self):
        self.receive_frame(self.close_frame)
        self.loop.run_until_complete(self.protocol.close(reason='close'))

        self.assertConnectionClosed(1000, 'close')
        self.assertOneFrameSent(*self.close_frame)

        # Closing the connection again is a no-op.
        self.loop.run_until_complete(self.protocol.close(reason='oh noes!'))

        self.assertConnectionClosed(1000, 'close')
        self.assertNoFrameSent()

    def test_client_close(self):
        self.receive_frame(self.close_frame)
        # The server is waiting for some data at this point but won't get it.
        next_message = self.loop.run_until_complete(self.protocol.recv())

        self.assertIsNone(next_message)
        # After recv() returns None, the connection is closed.
        self.assertConnectionClosed(1000, 'close')
        self.assertOneFrameSent(*self.close_frame)

        # Closing the connection again is a no-op.
        self.loop.run_until_complete(self.protocol.close(reason='oh noes!'))

        self.assertConnectionClosed(1000, 'close')
        self.assertNoFrameSent()

    def test_simultaneous_close(self):
        self.receive_frame(self.client_close)
        self.loop.run_until_complete(self.protocol.close(reason='server'))

        # The close code and reason are taken from the remote side because
        # that's presumably more useful that the values from the local side.
        self.assertConnectionClosed(1000, 'client')
        self.assertOneFrameSent(*self.server_close)

    def test_close_drops_frames(self):
        text_frame = Frame(True, OP_TEXT, b'')
        self.receive_frame(text_frame)
        self.receive_frame(self.close_frame)
        self.loop.run_until_complete(self.protocol.close(reason='close'))

        self.assertConnectionClosed(1000, 'close')
        self.assertOneFrameSent(*self.close_frame)

    def test_close_handshake_timeout(self):
        # Timeout is expected in 10ms.
        self.protocol.timeout = 10 * MS
        # Check the timing within -1/+9ms for robustness.
        with self.assertCompletesWithin(9 * MS, 19 * MS):
            # Unlike previous tests, no close frame will be received in
            # response. The server will stop waiting for the close frame and
            # timeout.
            self.loop.run_until_complete(self.protocol.close(reason='close'))
        self.assertConnectionClosed(1006, '')

    def test_client_close_race_with_failing_connection(self):
        self.make_drain_slow()

        # Fail the connection while answering a close frame from the client.
        self.loop.call_soon(self.receive_frame, self.client_close)
        self.loop.call_later(MS, self.async, self.protocol.fail_connection())
        next_message = self.loop.run_until_complete(self.protocol.recv())

        self.assertIsNone(next_message)
        # The closing handshake was completed by fail_connection.
        self.assertConnectionClosed(1011, '')
        self.assertOneFrameSent(*self.client_close)

    def test_close_protocol_error(self):
        invalid_close_frame = Frame(True, OP_CLOSE, b'\x00')
        self.receive_frame(invalid_close_frame)
        self.loop.run_until_complete(self.protocol.close(reason='close'))

        self.assertConnectionClosed(1002, '')

    def test_close_connection_lost(self):
        self.receive_eof()
        self.loop.run_until_complete(self.protocol.close(reason='close'))

        self.assertConnectionClosed(1006, '')

    def test_close_during_recv(self):
        recv = self.async(self.protocol.recv())
        self.receive_frame(self.close_frame)
        self.loop.run_until_complete(self.protocol.close(reason='close'))

        # Receiving a message shouldn't crash.
        next_message = self.loop.run_until_complete(recv)
        self.assertIsNone(next_message)

        self.assertConnectionClosed(1000, 'close')

    def test_close_during_send(self):
        self.make_drain_slow()

        send = self.async(self.protocol.send('hello'))
        self.receive_frame(self.close_frame)
        self.receive_eof()

        # Sending a message shouldn't crash.
        self.loop.run_until_complete(send)

        # Complete the connection.
        self.loop.run_until_complete(self.protocol.close(reason='close'))

        self.assertConnectionClosed(1006, '')


class ClientCloseTests(CommonTests, unittest.TestCase):

    def setUp(self):
        super().setUp()
        self.protocol.is_client = True

    def test_client_close(self):
        self.receive_frame(self.close_frame)
        self.receive_eof()
        self.loop.run_until_complete(self.protocol.close(reason='close'))

        self.assertConnectionClosed(1000, 'close')
        self.assertOneFrameSent(*self.close_frame)

        # Closing the connection again is a no-op.
        self.loop.run_until_complete(self.protocol.close(reason='oh noes!'))

        self.assertConnectionClosed(1000, 'close')
        self.assertNoFrameSent()

    def test_server_close(self):
        self.receive_frame(self.close_frame)
        self.receive_eof()
        # The client is waiting for some data at this point but won't get it.
        next_message = self.loop.run_until_complete(self.protocol.recv())

        self.assertIsNone(next_message)
        # After recv() returns None, the connection is closed.
        self.assertConnectionClosed(1000, 'close')
        self.assertOneFrameSent(*self.close_frame)

        # Closing the connection again is a no-op.
        self.loop.run_until_complete(self.protocol.close('oh noes!'))

        self.assertConnectionClosed(1000, 'close')
        self.assertNoFrameSent()

    def test_simultaneous_close(self):
        self.receive_frame(self.server_close)
        self.receive_eof()
        self.loop.run_until_complete(self.protocol.close(reason='client'))

        # The close code and reason are taken from the remote side because
        # that's presumably more useful that the values from the local side.
        self.assertConnectionClosed(1000, 'server')
        self.assertOneFrameSent(*self.client_close)

    def test_close_drops_frames(self):
        text_frame = Frame(True, OP_TEXT, b'')
        self.receive_frame(text_frame)
        self.receive_frame(self.close_frame)
        self.receive_eof()
        self.loop.run_until_complete(self.protocol.close(reason='close'))

        self.assertConnectionClosed(1000, 'close')
        self.assertOneFrameSent(*self.close_frame)

    def test_close_handshake_timeout(self):
        # Timeout is expected in 2 * 10 = 20ms.
        self.protocol.timeout = 10 * MS
        # Check the timing within -1/+9ms for robustness.
        with self.assertCompletesWithin(19 * MS, 29 * MS):
            # Unlike previous tests, no close frame will be received in
            # response and the connection will not be closed. The client will
            # stop waiting for the close frame and timeout, then stop waiting
            # for the connection close and timeout again.
            self.loop.run_until_complete(self.protocol.close(reason='close'))
        self.assertConnectionClosed(1006, '')

    def test_eof_received_timeout(self):
        # Timeout is expected in 10ms.
        self.protocol.timeout = 10 * MS
        # Check the timing within -1/+9ms for robustness.
        with self.assertCompletesWithin(9 * MS, 19 * MS):
            # Unlike previous tests, the close frame will be received in
            # response but the connection will not be closed. The client will
            # stop waiting for the connection close and timeout.
            self.receive_frame(self.close_frame)
            self.loop.run_until_complete(self.protocol.close(reason='close'))
        self.assertConnectionClosed(1000, 'close')

    def test_server_close_race_with_failing_connection(self):
        self.make_drain_slow()

        # Fail the connection while answering a close frame from the server.
        self.loop.call_soon(self.receive_frame, self.server_close)
        self.loop.call_later(MS, self.async, self.protocol.fail_connection())
        self.loop.call_later(2 * MS, self.receive_eof)
        next_message = self.loop.run_until_complete(self.protocol.recv())

        self.assertIsNone(next_message)
        # The closing handshake was completed by fail_connection.
        self.assertConnectionClosed(1011, '')
        self.assertOneFrameSent(*self.server_close)

    def test_close_protocol_error(self):
        invalid_close_frame = Frame(True, OP_CLOSE, b'\x00')
        self.receive_frame(invalid_close_frame)
        self.receive_eof()
        self.loop.run_until_complete(self.protocol.close(reason='close'))

        self.assertConnectionClosed(1002, '')

    def test_close_connection_lost(self):
        self.receive_eof()
        self.loop.run_until_complete(self.protocol.close(reason='close'))

        self.assertConnectionClosed(1006, '')

    def test_close_during_recv(self):
        recv = self.async(self.protocol.recv())
        self.receive_frame(self.close_frame)
        self.receive_eof()
        self.loop.run_until_complete(self.protocol.close(reason='close'))

        # Receiving a message shouldn't crash.
        next_message = self.loop.run_until_complete(recv)
        self.assertIsNone(next_message)

        self.assertConnectionClosed(1000, 'close')

    def test_close_during_send(self):
        self.make_drain_slow()

        send = self.async(self.protocol.send('hello'))
        self.receive_frame(self.close_frame)
        self.receive_eof()

        # Sending a message shouldn't crash.
        self.loop.run_until_complete(send)

        # Complete the connection.
        self.loop.run_until_complete(self.protocol.close(reason='close'))

        self.assertConnectionClosed(1006, '')
