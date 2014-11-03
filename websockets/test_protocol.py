import unittest
import unittest.mock

import asyncio

from .exceptions import InvalidState, PayloadTooBig
from .framing import *
from .protocol import WebSocketCommonProtocol


MS = 0.001          # Unit for timeouts. May be increased on slow machines.


class CommonTests:

    def setUp(self):
        super().setUp()
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.protocol = WebSocketCommonProtocol()
        self.transport = unittest.mock.Mock()
        self.transport._conn_lost = 0               # checked by drain()
        self.transport.close = unittest.mock.Mock(
                side_effect=lambda: self.protocol.connection_lost(None))
        self.protocol.connection_made(self.transport)

    def tearDown(self):
        self.loop.close()
        super().tearDown()

    def feed(self, frame):
        """Feed a frame to the protocol."""
        mask = not self.protocol.is_client
        write_frame(frame, self.protocol.data_received, mask)

    @asyncio.coroutine
    def sent(self):
        """Read the next frame sent to the transport."""
        stream = asyncio.StreamReader()
        for (data,), kw in self.transport.write.call_args_list:
            stream.feed_data(data)
        self.transport.write.call_args_list = []
        stream.feed_eof()
        if not stream.at_eof():
            return read_frame(stream.readexactly, self.protocol.is_client)

    @asyncio.coroutine
    def echo(self):
        """Echo to the protocol the next frame sent to the transport."""
        self.feed((yield from self.sent()))

    @asyncio.coroutine
    def fast_connection_failure(self):
        """Ensure the connection failure terminates quickly."""
        self.protocol.eof_received()
        self.protocol.connection_lost(None)

    def process_control_frames(self):
        """Process control frames fed to the protocol."""
        self.feed(Frame(True, OP_TEXT, b''))
        self.loop.run_until_complete(self.protocol.recv())

    def assertFrameSent(self, fin, opcode, data):
        sent = self.loop.run_until_complete(self.sent())
        self.assertEqual(sent, Frame(fin, opcode, data))

    def assertNoFrameSent(self):
        sent = self.loop.run_until_complete(self.sent())
        self.assertIsNone(sent)

    def assertConnectionClosed(self, code, message):
        self.assertEqual(self.protocol.state, 'CLOSED')
        self.assertEqual(self.protocol.close_code, code)
        self.assertEqual(self.protocol.close_reason, message)

    def test_open(self):
        self.assertTrue(self.protocol.open)
        self.protocol.connection_lost(None)
        self.assertFalse(self.protocol.open)

    def test_connection_lost(self):
        self.protocol.connection_lost(None)
        self.assertConnectionClosed(1006, '')

    def test_recv_text(self):
        self.feed(Frame(True, OP_TEXT, 'café'.encode('utf-8')))
        data = self.loop.run_until_complete(self.protocol.recv())
        self.assertEqual(data, 'café')

    def test_recv_binary(self):
        self.feed(Frame(True, OP_BINARY, b'tea'))
        data = self.loop.run_until_complete(self.protocol.recv())
        self.assertEqual(data, b'tea')

    def test_recv_protocol_error(self):
        self.feed(Frame(True, OP_CONT, 'café'.encode('utf-8')))
        self.loop.call_later(MS, asyncio.async, self.fast_connection_failure())
        self.assertIsNone(self.loop.run_until_complete(self.protocol.recv()))
        self.assertConnectionClosed(1002, '')

    def test_recv_unicode_error(self):
        self.feed(Frame(True, OP_TEXT, 'café'.encode('latin-1')))
        self.loop.call_later(MS, asyncio.async, self.fast_connection_failure())
        self.assertIsNone(self.loop.run_until_complete(self.protocol.recv()))
        self.assertConnectionClosed(1007, '')

    def test_recv_text_payload_too_big(self):
        self.protocol.max_size = 1024
        self.feed(Frame(True, OP_TEXT, 'café'.encode('utf-8') * 205))
        self.loop.call_later(MS, asyncio.async, self.fast_connection_failure())
        self.assertIsNone(self.loop.run_until_complete(self.protocol.recv()))
        self.assertConnectionClosed(1009, '')

    def test_recv_binary_payload_too_big(self):
        self.protocol.max_size = 1024
        self.feed(Frame(True, OP_BINARY, b'tea' * 342))
        self.loop.call_later(MS, asyncio.async, self.fast_connection_failure())
        self.assertIsNone(self.loop.run_until_complete(self.protocol.recv()))
        self.assertConnectionClosed(1009, '')

    def test_recv_text_no_max_size(self):
        self.protocol.max_size = None       # for test coverage
        self.feed(Frame(True, OP_TEXT, 'café'.encode('utf-8') * 205))
        data = self.loop.run_until_complete(self.protocol.recv())
        self.assertEqual(data, 'café' * 205)

    def test_recv_binary_no_max_size(self):
        self.protocol.max_size = None       # for test coverage
        self.feed(Frame(True, OP_BINARY, b'tea' * 342))
        data = self.loop.run_until_complete(self.protocol.recv())
        self.assertEqual(data, b'tea' * 342)

    def test_recv_other_error(self):
        @asyncio.coroutine
        def read_message():
            raise Exception("BOOM")
        self.protocol.read_message = read_message
        self.loop.call_later(MS, asyncio.async, self.fast_connection_failure())
        self.assertIsNone(self.loop.run_until_complete(self.protocol.recv()))
        with self.assertRaises(Exception):
            self.loop.run_until_complete(self.protocol.worker)
        self.assertConnectionClosed(1011, '')

    def test_recv_on_closed_connection(self):
        self.protocol.eof_received()
        self.protocol.connection_lost(None)
        self.assertIsNone(self.loop.run_until_complete(self.protocol.recv()))

    def test_send_text(self):
        self.loop.run_until_complete(self.protocol.send('café'))
        self.assertFrameSent(True, OP_TEXT, 'café'.encode('utf-8'))

    def test_send_binary(self):
        self.loop.run_until_complete(self.protocol.send(b'tea'))
        self.assertFrameSent(True, OP_BINARY, b'tea')

    def test_send_type_error(self):
        with self.assertRaises(TypeError):
            self.loop.run_until_complete(self.protocol.send(42))
        self.assertNoFrameSent()

    def test_send_on_closed_connection(self):
        self.protocol.eof_received()
        self.protocol.connection_lost(None)
        with self.assertRaises(InvalidState):
            self.loop.run_until_complete(self.protocol.send('foobar'))
        self.assertNoFrameSent()

    def test_answer_ping(self):
        self.feed(Frame(True, OP_PING, b'test'))
        self.process_control_frames()
        self.assertFrameSent(True, OP_PONG, b'test')

    def test_ignore_pong(self):
        self.feed(Frame(True, OP_PONG, b'test'))
        self.process_control_frames()
        self.assertNoFrameSent()

    def test_acknowledge_ping(self):
        ping = self.loop.run_until_complete(self.protocol.ping())
        self.assertFalse(ping.done())
        ping_frame = self.loop.run_until_complete(self.sent())
        pong_frame = Frame(True, OP_PONG, ping_frame.data)
        self.feed(pong_frame)
        self.process_control_frames()
        self.assertTrue(ping.done())

    def test_acknowledge_previous_pings(self):
        pings = [(
            self.loop.run_until_complete(self.protocol.ping()),
            self.loop.run_until_complete(self.sent()),
        ) for i in range(3)]
        # Unsolicited pong doesn't acknowledge pings
        self.feed(Frame(True, OP_PONG, b''))
        self.process_control_frames()
        self.assertFalse(pings[0][0].done())
        self.assertFalse(pings[1][0].done())
        self.assertFalse(pings[2][0].done())
        # Pong acknowledges all previous pings
        self.feed(Frame(True, OP_PONG, pings[1][1].data))
        self.process_control_frames()
        self.assertTrue(pings[0][0].done())
        self.assertTrue(pings[1][0].done())
        self.assertFalse(pings[2][0].done())

    def test_cancel_ping(self):
        ping = self.loop.run_until_complete(self.protocol.ping())
        ping_frame = self.loop.run_until_complete(self.sent())
        ping.cancel()
        pong_frame = Frame(True, OP_PONG, ping_frame.data)
        self.feed(pong_frame)
        self.process_control_frames()
        self.assertTrue(ping.cancelled())

    def test_duplicate_ping(self):
        self.loop.run_until_complete(self.protocol.ping(b'foobar'))
        self.assertFrameSent(True, OP_PING, b'foobar')
        with self.assertRaises(ValueError):
            self.loop.run_until_complete(self.protocol.ping(b'foobar'))
        self.assertNoFrameSent()

    def test_fragmented_text(self):
        self.feed(Frame(False, OP_TEXT, 'ca'.encode('utf-8')))
        self.feed(Frame(True, OP_CONT, 'fé'.encode('utf-8')))
        data = self.loop.run_until_complete(self.protocol.recv())
        self.assertEqual(data, 'café')

    def test_fragmented_binary(self):
        self.feed(Frame(False, OP_BINARY, b't'))
        self.feed(Frame(False, OP_CONT, b'e'))
        self.feed(Frame(True, OP_CONT, b'a'))
        data = self.loop.run_until_complete(self.protocol.recv())
        self.assertEqual(data, b'tea')

    def test_fragmented_text_payload_too_big(self):
        self.protocol.max_size = 1024
        self.feed(Frame(False, OP_TEXT, 'café'.encode('utf-8') * 100))
        self.feed(Frame(True, OP_CONT, 'café'.encode('utf-8') * 105))
        self.loop.call_later(MS, asyncio.async, self.fast_connection_failure())
        self.assertIsNone(self.loop.run_until_complete(self.protocol.recv()))
        self.assertConnectionClosed(1009, '')

    def test_fragmented_binary_payload_too_big(self):
        self.protocol.max_size = 1024
        self.feed(Frame(False, OP_BINARY, b'tea' * 171))
        self.feed(Frame(True, OP_CONT, b'tea' * 171))
        self.loop.call_later(MS, asyncio.async, self.fast_connection_failure())
        self.assertIsNone(self.loop.run_until_complete(self.protocol.recv()))
        self.assertConnectionClosed(1009, '')

    def test_fragmented_text_no_max_size(self):
        self.protocol.max_size = None       # for test coverage
        self.feed(Frame(False, OP_TEXT, 'café'.encode('utf-8') * 100))
        self.feed(Frame(True, OP_CONT, 'café'.encode('utf-8') * 105))
        data = self.loop.run_until_complete(self.protocol.recv())
        self.assertEqual(data, 'café' * 205)

    def test_fragmented_binary_no_max_size(self):
        self.protocol.max_size = None       # for test coverage
        self.feed(Frame(False, OP_BINARY, b'tea' * 171))
        self.feed(Frame(True, OP_CONT, b'tea' * 171))
        data = self.loop.run_until_complete(self.protocol.recv())
        self.assertEqual(data, b'tea' * 342)

    def test_control_frame_within_fragmented_text(self):
        self.feed(Frame(False, OP_TEXT, 'ca'.encode('utf-8')))
        self.feed(Frame(True, OP_PING, b''))
        self.feed(Frame(True, OP_CONT, 'fé'.encode('utf-8')))
        data = self.loop.run_until_complete(self.protocol.recv())
        self.assertEqual(data, 'café')
        self.assertFrameSent(True, OP_PONG, b'')

    def test_unterminated_fragmented_text(self):
        self.feed(Frame(False, OP_TEXT, 'ca'.encode('utf-8')))
        # Missing the second part of the fragmented frame.
        self.feed(Frame(True, OP_BINARY, b'tea'))
        self.loop.call_later(MS, asyncio.async, self.fast_connection_failure())
        self.assertIsNone(self.loop.run_until_complete(self.protocol.recv()))
        self.assertConnectionClosed(1002, '')

    def test_close_handshake_in_fragmented_text(self):
        self.feed(Frame(False, OP_TEXT, 'ca'.encode('utf-8')))
        self.feed(Frame(True, OP_CLOSE, b''))
        self.loop.call_later(MS, asyncio.async, self.fast_connection_failure())
        self.assertIsNone(self.loop.run_until_complete(self.protocol.recv()))
        self.assertConnectionClosed(1002, '')

    def test_connection_close_in_fragmented_text(self):
        self.feed(Frame(False, OP_TEXT, 'ca'.encode('utf-8')))
        self.loop.call_later(MS, self.protocol.eof_received)
        self.loop.call_later(2 * MS, lambda: self.protocol.connection_lost(None))
        self.assertIsNone(self.loop.run_until_complete(self.protocol.recv()))
        self.assertConnectionClosed(1006, '')


class ServerTests(CommonTests, unittest.TestCase):

    def test_close(self):               # standard server-initiated close
        self.loop.call_later(MS, asyncio.async, self.echo())
        self.loop.run_until_complete(self.protocol.close(reason='because.'))
        self.assertConnectionClosed(1000, 'because.')
        # Only one frame is emitted, and it's consumed by self.echo().
        self.assertNoFrameSent()
        # Closing the connection again is a no-op.
        self.loop.run_until_complete(self.protocol.close(reason='oh noes!'))
        self.assertConnectionClosed(1000, 'because.')
        self.assertNoFrameSent()

    def test_client_close(self):        # non standard client-initiated close
        frame = Frame(True, OP_CLOSE, serialize_close(1000, 'because.'))
        self.loop.call_later(MS, self.feed, frame)
        # The server is waiting for some data at this point, and won't get it.
        self.assertIsNone(self.loop.run_until_complete(self.protocol.recv()))
        # After recv() returns None, the connection is closed.
        self.assertConnectionClosed(1000, 'because.')
        self.assertFrameSent(*frame)
        # Closing the connection again is a no-op.
        self.loop.run_until_complete(self.protocol.close(reason='oh noes!'))
        self.assertConnectionClosed(1000, 'because.')
        self.assertNoFrameSent()

    def test_simultaneous_close(self):  # non standard close from both sides
        client_close = Frame(True, OP_CLOSE, serialize_close(1000, 'client'))
        server_close = Frame(True, OP_CLOSE, serialize_close(1000, 'server'))
        self.loop.call_later(MS, self.feed, client_close)
        self.loop.run_until_complete(self.protocol.close(reason='server'))
        self.assertConnectionClosed(1000, 'client')
        self.assertFrameSent(*server_close)
        self.assertNoFrameSent()

    def test_close_drops_frames(self):
        self.loop.call_later(MS, self.feed, Frame(True, OP_TEXT, b''))
        self.loop.call_later(2 * MS, asyncio.async, self.echo())
        self.loop.run_until_complete(self.protocol.close(reason='because.'))
        self.assertConnectionClosed(1000, 'because.')
        # Only one frame is emitted, and it's consumed by self.echo().
        self.assertNoFrameSent()

    def test_close_handshake_timeout(self):
        self.after = asyncio.Future()
        self.loop.call_later(4 * MS, self.after.cancel)
        self.before = asyncio.Future()
        self.loop.call_later(8 * MS, self.before.cancel)
        self.protocol.timeout = 5 * MS
        self.loop.run_until_complete(self.protocol.close(reason='because.'))
        self.assertConnectionClosed(1000, 'because.')
        self.assertTrue(self.after.cancelled())
        self.assertFalse(self.before.cancelled())
        self.before.cancel()

    def test_close_timeout_before_connection_lost(self):
        # Prevent the connection from terminating.
        self.protocol.connection_lost = unittest.mock.Mock()

        self.after = asyncio.Future()
        self.loop.call_later(4 * MS, self.after.cancel)
        self.before = asyncio.Future()
        self.loop.call_later(8 * MS, self.before.cancel)
        self.protocol.timeout = 5 * MS
        self.loop.call_later(MS, asyncio.async, self.echo())
        self.loop.run_until_complete(self.protocol.close(reason='because.'))
        self.assertEqual(self.protocol.state, 'CLOSING')
        self.assertTrue(self.after.cancelled())
        self.assertFalse(self.before.cancelled())
        self.before.cancel()

    def test_client_close_race_with_failing_connection(self):
        original_write_frame = self.protocol.write_frame
        @asyncio.coroutine
        def delayed_write_frame(*args):
            yield from original_write_frame(*args)
            yield from asyncio.sleep(2 * MS)
        self.protocol.write_frame = delayed_write_frame

        frame = Frame(True, OP_CLOSE, serialize_close(1000, 'client'))
        # Trigger the race condition between answering the close frame from
        # the client and sending another close frame from the server.
        self.loop.call_later(MS, self.feed, frame)
        self.loop.call_later(2 * MS, asyncio.async, self.protocol.fail_connection(1000, 'server'))
        self.assertIsNone(self.loop.run_until_complete(self.protocol.recv()))
        self.assertConnectionClosed(1000, 'server')
        self.assertFrameSent(*frame)

    def test_close_protocol_error(self):
        self.loop.call_later(MS, self.feed, Frame(True, OP_CLOSE, b'\x00'))
        self.loop.run_until_complete(self.protocol.close(reason='because.'))
        self.assertConnectionClosed(1002, '')

    def test_close_connection_lost(self):
        self.loop.call_later(MS, self.protocol.eof_received)
        self.loop.call_later(2 * MS, lambda: self.protocol.connection_lost(None))
        self.loop.run_until_complete(self.protocol.close(reason='because.'))
        self.assertConnectionClosed(1006, '')

    def test_close_during_recv(self):
        recv = asyncio.async(self.protocol.recv())
        self.loop.call_later(MS, asyncio.async, self.echo())
        self.loop.run_until_complete(self.protocol.close(reason='because.'))
        self.assertIsNone(self.loop.run_until_complete(recv))

    def test_close_after_cancelled_recv(self):
        recv = asyncio.async(self.protocol.recv())
        self.loop.call_later(MS, recv.cancel)
        with self.assertRaises(asyncio.CancelledError):
            self.loop.run_until_complete(recv)
        # Closing the connection shouldn't crash.
        # I can't find a way to test this on the client side.
        self.loop.call_later(MS, asyncio.async, self.echo())
        self.loop.run_until_complete(self.protocol.close(reason='because.'))


class ClientTests(CommonTests, unittest.TestCase):

    def setUp(self):
        super().setUp()
        self.protocol.is_client = True

    def test_close(self):               # standard server-initiated close
        frame = Frame(True, OP_CLOSE, serialize_close(1000, 'because.'))
        self.loop.call_later(MS, self.feed, frame)
        self.loop.call_later(2 * MS, self.protocol.eof_received)
        self.loop.call_later(3 * MS, lambda: self.protocol.connection_lost(None))
        # The client is waiting for some data at this point, and won't get it.
        self.assertIsNone(self.loop.run_until_complete(self.protocol.recv()))
        # After recv() returns None, the connection is closed.
        self.assertConnectionClosed(1000, 'because.')
        self.assertFrameSent(*frame)
        # Closing the connection again is a no-op.
        self.loop.run_until_complete(self.protocol.close('oh noes!'))
        self.assertConnectionClosed(1000, 'because.')
        self.assertNoFrameSent()

    def test_client_close(self):        # non standard client-initiated close
        self.loop.call_later(MS, asyncio.async, self.echo())
        self.loop.call_later(2 * MS, self.protocol.eof_received)
        self.loop.call_later(3 * MS, lambda: self.protocol.connection_lost(None))
        self.loop.run_until_complete(self.protocol.close(reason='because.'))
        self.assertConnectionClosed(1000, 'because.')
        # Only one frame is emitted, and it's consumed by self.echo().
        self.assertNoFrameSent()
        # Closing the connection again is a no-op.
        self.loop.run_until_complete(self.protocol.close(reason='oh noes!'))
        self.assertConnectionClosed(1000, 'because.')
        self.assertNoFrameSent()

    def test_simultaneous_close(self):  # non standard close from both sides
        server_close = Frame(True, OP_CLOSE, serialize_close(1000, 'server'))
        client_close = Frame(True, OP_CLOSE, serialize_close(1000, 'client'))
        self.loop.call_later(MS, self.feed, server_close)
        self.loop.call_later(2 * MS, self.protocol.eof_received)
        self.loop.call_later(3 * MS, lambda: self.protocol.connection_lost(None))
        self.loop.run_until_complete(self.protocol.close(reason='client'))
        self.assertConnectionClosed(1000, 'server')
        self.assertFrameSent(*client_close)
        self.assertNoFrameSent()

    def test_close_timeout_before_eof_received(self):
        self.after = asyncio.Future()
        self.loop.call_later(4 * MS, self.after.cancel)
        self.before = asyncio.Future()
        self.loop.call_later(8 * MS, self.before.cancel)
        self.protocol.timeout = 5 * MS
        self.loop.call_later(MS, asyncio.async, self.echo())
        self.loop.run_until_complete(self.protocol.close(reason='because.'))
        # If the server doesn't drop the connection quickly, the client will.
        self.assertConnectionClosed(1000, 'because.')
        self.assertTrue(self.after.cancelled())
        self.assertFalse(self.before.cancelled())
        self.before.cancel()

    def test_close_timeout_before_connection_lost(self):
        # Prevent the connection from terminating.
        self.protocol.connection_lost = unittest.mock.Mock()

        self.after = asyncio.Future()
        self.loop.call_later(9 * MS, self.after.cancel)
        self.before = asyncio.Future()
        self.loop.call_later(13 * MS, self.before.cancel)
        self.protocol.timeout = 5 * MS
        self.loop.call_later(MS, asyncio.async, self.echo())
        self.loop.call_later(2 * MS, self.protocol.eof_received)
        self.loop.run_until_complete(self.protocol.close(reason='because.'))
        # If the server doesn't drop the connection quickly, the client will.
        self.assertEqual(self.protocol.state, 'CLOSING')
        self.assertTrue(self.after.cancelled())
        self.assertFalse(self.before.cancelled())
        self.before.cancel()

    def test_server_close_race_with_failing_connection(self):
        original_write_frame = self.protocol.write_frame
        @asyncio.coroutine
        def delayed_write_frame(*args):
            yield from original_write_frame(*args)
            yield from asyncio.sleep(2 * MS)
        self.protocol.write_frame = delayed_write_frame

        frame = Frame(True, OP_CLOSE, serialize_close(1000, 'server'))
        # Trigger the race condition between answering the close frame from
        # the server and sending another close frame from the client.
        self.loop.call_later(MS, self.feed, frame)
        self.loop.call_later(2 * MS, asyncio.async, self.protocol.fail_connection(1000, 'client'))
        self.loop.call_later(3 * MS, self.protocol.eof_received)
        self.loop.call_later(4 * MS, lambda: self.protocol.connection_lost(None))
        self.assertIsNone(self.loop.run_until_complete(self.protocol.recv()))
        self.assertConnectionClosed(1000, 'client')
        self.assertFrameSent(*frame)
