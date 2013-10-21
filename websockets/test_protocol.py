import unittest
import unittest.mock

import asyncio

from .exceptions import InvalidState
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

    def feed_eof(self):
        """Feed end-of-file to the protocol."""
        # The transport is mocked so this sequence will happen synchronously:
        # proto.eof_received() -> transport.close() -> proto.connection_lost()
        # To allow processing frames before shutting down the connection,
        # delay self.feed_eof() with self.loop.call_later().
        self.protocol.eof_received()

    @asyncio.coroutine
    def sent(self):
        """Read the next frame sent to the transport."""
        stream = asyncio.StreamReader()
        for (data,), kw in self.transport.write.call_args_list:
            stream.feed_data(data)
        self.transport.write.call_args_list = []
        stream.feed_eof()
        if stream._byte_count:
            return read_frame(stream.readexactly, self.protocol.is_client)

    @asyncio.coroutine
    def echo(self):
        """Echo to the protocol the next frame sent to the transport."""
        self.feed((yield from self.sent()))

    @asyncio.coroutine
    def fast_connection_failure(self):
        """Ensure the connection failure terminates quickly."""
        sent = yield from self.sent()
        if sent and sent.opcode == OP_CLOSE:
            self.feed(sent)
            if self.protocol.is_client:
                self.feed_eof()

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
        self.feed_eof()
        self.assertFalse(self.protocol.open)

    def test_connection_lost(self):
        self.feed_eof()
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
        self.feed_eof()
        self.assertIsNone(self.loop.run_until_complete(self.protocol.recv()))

    def test_send_text(self):
        self.protocol.send('café')
        self.assertFrameSent(True, OP_TEXT, 'café'.encode('utf-8'))

    def test_send_binary(self):
        self.protocol.send(b'tea')
        self.assertFrameSent(True, OP_BINARY, b'tea')

    def test_send_type_error(self):
        with self.assertRaises(TypeError):
            self.protocol.send(42)
        self.assertNoFrameSent()

    def test_send_on_closed_connection(self):
        self.feed_eof()
        with self.assertRaises(InvalidState):
            self.protocol.send('foobar')
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
        ping = self.protocol.ping()
        self.assertFalse(ping.done())
        ping_frame = self.loop.run_until_complete(self.sent())
        pong_frame = Frame(True, OP_PONG, ping_frame.data)
        self.feed(pong_frame)
        self.process_control_frames()
        self.assertTrue(ping.done())

    def test_acknowledge_previous_pings(self):
        pings = [(
            self.protocol.ping(),
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

    def test_duplicate_ping(self):
        self.protocol.ping(b'foobar')
        self.assertFrameSent(True, OP_PING, b'foobar')
        with self.assertRaises(ValueError):
            self.protocol.ping(b'foobar')
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
        self.loop.call_later(MS, self.feed_eof)
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
        # After recv() returns None the connection is closed.
        self.assertConnectionClosed(1000, 'because.')
        self.assertFrameSent(*frame)
        # The server may call close() later without any effect.
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

    def test_close_timeout(self):
        self.after = asyncio.Future()
        self.loop.call_later(2 * MS, self.after.cancel)
        self.before = asyncio.Future()
        self.loop.call_later(10 * MS, self.before.cancel)
        self.protocol.timeout = 5 * MS
        self.loop.run_until_complete(self.protocol.close(reason='because.'))
        self.assertConnectionClosed(1000, 'because.')
        self.assertTrue(self.after.cancelled())
        self.assertFalse(self.before.cancelled())
        self.before.cancel()

    def test_close_protocol_error(self):
        self.loop.call_later(MS, self.feed, Frame(True, OP_CLOSE, b'\x00'))
        self.loop.run_until_complete(self.protocol.close(reason='because.'))
        self.assertConnectionClosed(1002, '')

    def test_close_connection_lost(self):
        self.loop.call_later(MS, self.feed_eof)
        self.loop.run_until_complete(self.protocol.close(reason='because.'))
        self.assertConnectionClosed(1002, '')

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
        self.loop.call_later(2 * MS, self.feed_eof)
        # The client is waiting for some data at this point, and won't get it.
        self.assertIsNone(self.loop.run_until_complete(self.protocol.recv()))
        # After recv() returns None the connection is closed.
        self.assertConnectionClosed(1000, 'because.')
        self.assertFrameSent(*frame)
        # The client may call close() later without any effect.
        self.loop.run_until_complete(self.protocol.close('oh noes!'))
        self.assertConnectionClosed(1000, 'because.')
        self.assertNoFrameSent()

    def test_client_close(self):        # non standard client-initiated close
        self.loop.call_later(MS, asyncio.async, self.echo())
        self.loop.call_later(2 * MS, self.feed_eof)
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
        self.loop.call_later(2 * MS, self.feed_eof)
        self.loop.run_until_complete(self.protocol.close(reason='client'))
        self.assertConnectionClosed(1000, 'server')
        self.assertFrameSent(*client_close)
        self.assertNoFrameSent()

    def test_connection_close_timeout(self):
        # If the server doesn't drop the connection quickly, the client will.
        self.after = asyncio.Future()
        self.loop.call_later(2 * MS, self.after.cancel)
        self.before = asyncio.Future()
        self.loop.call_later(10 * MS, self.before.cancel)
        self.protocol.timeout = 5 * MS
        self.loop.call_later(MS, asyncio.async, self.echo())
        self.loop.run_until_complete(self.protocol.close(reason='because.'))
        self.assertConnectionClosed(1000, 'because.')
        self.assertTrue(self.after.cancelled())
        self.assertFalse(self.before.cancelled())
        self.before.cancel()
