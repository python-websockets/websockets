import asyncio
import contextlib
import logging
import socket
import unittest
import uuid
from unittest.mock import patch

from websockets.asyncio.compatibility import TimeoutError, aiter, anext, asyncio_timeout
from websockets.asyncio.connection import *
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK
from websockets.frames import CloseCode, Frame, Opcode
from websockets.protocol import CLIENT, SERVER, Protocol

from ..protocol import RecordingProtocol
from ..utils import MS
from .connection import InterceptingConnection
from .utils import alist


# Connection implements symmetrical behavior between clients and servers.
# All tests run on the client side and the server side to validate this.


class ClientConnectionTests(unittest.IsolatedAsyncioTestCase):
    LOCAL = CLIENT
    REMOTE = SERVER

    async def asyncSetUp(self):
        loop = asyncio.get_running_loop()
        socket_, remote_socket = socket.socketpair()
        self.transport, self.connection = await loop.create_connection(
            lambda: Connection(Protocol(self.LOCAL), close_timeout=2 * MS),
            sock=socket_,
        )
        self.remote_transport, self.remote_connection = await loop.create_connection(
            lambda: InterceptingConnection(RecordingProtocol(self.REMOTE)),
            sock=remote_socket,
        )

    async def asyncTearDown(self):
        await self.remote_connection.close()
        await self.connection.close()

    # Test helpers built upon RecordingProtocol and InterceptingConnection.

    async def assertFrameSent(self, frame):
        """Check that a single frame was sent."""
        # Let the remote side process messages.
        # Two runs of the event loop are required for answering pings.
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        self.assertEqual(self.remote_connection.protocol.get_frames_rcvd(), [frame])

    async def assertFramesSent(self, frames):
        """Check that several frames were sent."""
        # Let the remote side process messages.
        # Two runs of the event loop are required for answering pings.
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        self.assertEqual(self.remote_connection.protocol.get_frames_rcvd(), frames)

    async def assertNoFrameSent(self):
        """Check that no frame was sent."""
        # Run the event loop twice for consistency with assertFrameSent.
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        self.assertEqual(self.remote_connection.protocol.get_frames_rcvd(), [])

    @contextlib.asynccontextmanager
    async def delay_frames_rcvd(self, delay):
        """Delay frames before they're received by the connection."""
        with self.remote_connection.delay_frames_sent(delay):
            yield
            await asyncio.sleep(MS)  # let the remote side process messages

    @contextlib.asynccontextmanager
    async def delay_eof_rcvd(self, delay):
        """Delay EOF before it's received by the connection."""
        with self.remote_connection.delay_eof_sent(delay):
            yield
            await asyncio.sleep(MS)  # let the remote side process messages

    @contextlib.asynccontextmanager
    async def drop_frames_rcvd(self):
        """Drop frames before they're received by the connection."""
        with self.remote_connection.drop_frames_sent():
            yield
            await asyncio.sleep(MS)  # let the remote side process messages

    @contextlib.asynccontextmanager
    async def drop_eof_rcvd(self):
        """Drop EOF before it's received by the connection."""
        with self.remote_connection.drop_eof_sent():
            yield
            await asyncio.sleep(MS)  # let the remote side process messages

    # Test __aenter__ and __aexit__.

    async def test_aenter(self):
        """__aenter__ returns the connection itself."""
        async with self.connection as connection:
            self.assertIs(connection, self.connection)

    async def test_aexit(self):
        """__aexit__ closes the connection with code 1000."""
        async with self.connection:
            await self.assertNoFrameSent()
        await self.assertFrameSent(Frame(Opcode.CLOSE, b"\x03\xe8"))

    async def test_exit_with_exception(self):
        """__exit__ with an exception closes the connection with code 1011."""
        with self.assertRaises(RuntimeError):
            async with self.connection:
                raise RuntimeError
        await self.assertFrameSent(Frame(Opcode.CLOSE, b"\x03\xf3"))

    # Test __aiter__.

    async def test_aiter_text(self):
        """__aiter__ yields text messages."""
        aiterator = aiter(self.connection)
        await self.remote_connection.send("😀")
        self.assertEqual(await anext(aiterator), "😀")
        await self.remote_connection.send("😀")
        self.assertEqual(await anext(aiterator), "😀")

    async def test_aiter_binary(self):
        """__aiter__ yields binary messages."""
        aiterator = aiter(self.connection)
        await self.remote_connection.send(b"\x01\x02\xfe\xff")
        self.assertEqual(await anext(aiterator), b"\x01\x02\xfe\xff")
        await self.remote_connection.send(b"\x01\x02\xfe\xff")
        self.assertEqual(await anext(aiterator), b"\x01\x02\xfe\xff")

    async def test_aiter_mixed(self):
        """__aiter__ yields a mix of text and binary messages."""
        aiterator = aiter(self.connection)
        await self.remote_connection.send("😀")
        self.assertEqual(await anext(aiterator), "😀")
        await self.remote_connection.send(b"\x01\x02\xfe\xff")
        self.assertEqual(await anext(aiterator), b"\x01\x02\xfe\xff")

    async def test_aiter_connection_closed_ok(self):
        """__aiter__ terminates after a normal closure."""
        aiterator = aiter(self.connection)
        await self.remote_connection.close()
        with self.assertRaises(StopAsyncIteration):
            await anext(aiterator)

    async def test_aiter_connection_closed_error(self):
        """__aiter__ raises ConnnectionClosedError after an error."""
        aiterator = aiter(self.connection)
        await self.remote_connection.close(code=CloseCode.INTERNAL_ERROR)
        with self.assertRaises(ConnectionClosedError):
            await anext(aiterator)

    # Test recv.

    async def test_recv_text(self):
        """recv receives a text message."""
        await self.remote_connection.send("😀")
        self.assertEqual(await self.connection.recv(), "😀")

    async def test_recv_binary(self):
        """recv receives a binary message."""
        await self.remote_connection.send(b"\x01\x02\xfe\xff")
        self.assertEqual(await self.connection.recv(), b"\x01\x02\xfe\xff")

    async def test_recv_fragmented_text(self):
        """recv receives a fragmented text message."""
        await self.remote_connection.send(["😀", "😀"])
        self.assertEqual(await self.connection.recv(), "😀😀")

    async def test_recv_fragmented_binary(self):
        """recv receives a fragmented binary message."""
        await self.remote_connection.send([b"\x01\x02", b"\xfe\xff"])
        self.assertEqual(await self.connection.recv(), b"\x01\x02\xfe\xff")

    async def test_recv_connection_closed_ok(self):
        """recv raises ConnectionClosedOK after a normal closure."""
        await self.remote_connection.close()
        with self.assertRaises(ConnectionClosedOK):
            await self.connection.recv()

    async def test_recv_connection_closed_error(self):
        """recv raises ConnectionClosedError after an error."""
        await self.remote_connection.close(code=CloseCode.INTERNAL_ERROR)
        with self.assertRaises(ConnectionClosedError):
            await self.connection.recv()

    async def test_recv_during_recv(self):
        """recv raises RuntimeError when called concurrently with itself."""
        recv_task = asyncio.create_task(self.connection.recv())
        await asyncio.sleep(0)  # let the event loop start recv_task
        self.addCleanup(recv_task.cancel)

        with self.assertRaises(RuntimeError) as raised:
            await self.connection.recv()
        self.assertEqual(
            str(raised.exception),
            "cannot call recv while another coroutine "
            "is already running recv or recv_streaming",
        )

    async def test_recv_during_recv_streaming(self):
        """recv raises RuntimeError when called concurrently with recv_streaming."""
        recv_streaming_task = asyncio.create_task(
            alist(self.connection.recv_streaming())
        )
        await asyncio.sleep(0)  # let the event loop start recv_streaming_task
        self.addCleanup(recv_streaming_task.cancel)

        with self.assertRaises(RuntimeError) as raised:
            await self.connection.recv()
        self.assertEqual(
            str(raised.exception),
            "cannot call recv while another coroutine "
            "is already running recv or recv_streaming",
        )

    async def test_recv_cancellation_before_receiving(self):
        """recv can be cancelled before receiving a frame."""
        recv_task = asyncio.create_task(self.connection.recv())
        await asyncio.sleep(0)  # let the event loop start recv_task

        recv_task.cancel()
        await asyncio.sleep(0)  # let the event loop cancel recv_task

        # Running recv again receives the next message.
        await self.remote_connection.send("😀")
        self.assertEqual(await self.connection.recv(), "😀")

    async def test_recv_cancellation_while_receiving(self):
        """recv cannot be cancelled after receiving a frame."""
        recv_task = asyncio.create_task(self.connection.recv())
        await asyncio.sleep(0)  # let the event loop start recv_task

        gate = asyncio.get_running_loop().create_future()

        async def fragments():
            yield "⏳"
            await gate
            yield "⌛️"

        asyncio.create_task(self.remote_connection.send(fragments()))
        await asyncio.sleep(MS)

        recv_task.cancel()
        await asyncio.sleep(0)  # let the event loop cancel recv_task

        # Running recv again receives the complete message.
        gate.set_result(None)
        self.assertEqual(await self.connection.recv(), "⏳⌛️")

    # Test recv_streaming.

    async def test_recv_streaming_text(self):
        """recv_streaming receives a text message."""
        await self.remote_connection.send("😀")
        self.assertEqual(
            await alist(self.connection.recv_streaming()),
            ["😀"],
        )

    async def test_recv_streaming_binary(self):
        """recv_streaming receives a binary message."""
        await self.remote_connection.send(b"\x01\x02\xfe\xff")
        self.assertEqual(
            await alist(self.connection.recv_streaming()),
            [b"\x01\x02\xfe\xff"],
        )

    async def test_recv_streaming_fragmented_text(self):
        """recv_streaming receives a fragmented text message."""
        await self.remote_connection.send(["😀", "😀"])
        # websockets sends an trailing empty fragment. That's an implementation detail.
        self.assertEqual(
            await alist(self.connection.recv_streaming()),
            ["😀", "😀", ""],
        )

    async def test_recv_streaming_fragmented_binary(self):
        """recv_streaming receives a fragmented binary message."""
        await self.remote_connection.send([b"\x01\x02", b"\xfe\xff"])
        # websockets sends an trailing empty fragment. That's an implementation detail.
        self.assertEqual(
            await alist(self.connection.recv_streaming()),
            [b"\x01\x02", b"\xfe\xff", b""],
        )

    async def test_recv_streaming_connection_closed_ok(self):
        """recv_streaming raises ConnectionClosedOK after a normal closure."""
        await self.remote_connection.close()
        with self.assertRaises(ConnectionClosedOK):
            async for _ in self.connection.recv_streaming():
                self.fail("did not raise")

    async def test_recv_streaming_connection_closed_error(self):
        """recv_streaming raises ConnectionClosedError after an error."""
        await self.remote_connection.close(code=CloseCode.INTERNAL_ERROR)
        with self.assertRaises(ConnectionClosedError):
            async for _ in self.connection.recv_streaming():
                self.fail("did not raise")

    async def test_recv_streaming_during_recv(self):
        """recv_streaming raises RuntimeError when called concurrently with recv."""
        recv_task = asyncio.create_task(self.connection.recv())
        await asyncio.sleep(0)  # let the event loop start recv_task
        self.addCleanup(recv_task.cancel)

        with self.assertRaises(RuntimeError) as raised:
            async for _ in self.connection.recv_streaming():
                self.fail("did not raise")
        self.assertEqual(
            str(raised.exception),
            "cannot call recv_streaming while another coroutine "
            "is already running recv or recv_streaming",
        )

    async def test_recv_streaming_during_recv_streaming(self):
        """recv_streaming raises RuntimeError when called concurrently with itself."""
        recv_streaming_task = asyncio.create_task(
            alist(self.connection.recv_streaming())
        )
        await asyncio.sleep(0)  # let the event loop start recv_streaming_task
        self.addCleanup(recv_streaming_task.cancel)

        with self.assertRaises(RuntimeError) as raised:
            async for _ in self.connection.recv_streaming():
                self.fail("did not raise")
        self.assertEqual(
            str(raised.exception),
            r"cannot call recv_streaming while another coroutine "
            r"is already running recv or recv_streaming",
        )

    async def test_recv_streaming_cancellation_before_receiving(self):
        """recv_streaming can be cancelled before receiving a frame."""
        recv_streaming_task = asyncio.create_task(
            alist(self.connection.recv_streaming())
        )
        await asyncio.sleep(0)  # let the event loop start recv_streaming_task

        recv_streaming_task.cancel()
        await asyncio.sleep(0)  # let the event loop cancel recv_streaming_task

        # Running recv_streaming again receives the next message.
        await self.remote_connection.send(["😀", "😀"])
        self.assertEqual(
            await alist(self.connection.recv_streaming()),
            ["😀", "😀", ""],
        )

    async def test_recv_streaming_cancellation_while_receiving(self):
        """recv_streaming cannot be cancelled after receiving a frame."""
        recv_streaming_task = asyncio.create_task(
            alist(self.connection.recv_streaming())
        )
        await asyncio.sleep(0)  # let the event loop start recv_streaming_task

        gate = asyncio.get_running_loop().create_future()

        async def fragments():
            yield "⏳"
            await gate
            yield "⌛️"

        asyncio.create_task(self.remote_connection.send(fragments()))
        await asyncio.sleep(MS)

        recv_streaming_task.cancel()
        await asyncio.sleep(0)  # let the event loop cancel recv_streaming_task

        gate.set_result(None)
        # Running recv_streaming again fails.
        with self.assertRaises(RuntimeError):
            await alist(self.connection.recv_streaming())

    # Test send.

    async def test_send_text(self):
        """send sends a text message."""
        await self.connection.send("😀")
        self.assertEqual(await self.remote_connection.recv(), "😀")

    async def test_send_binary(self):
        """send sends a binary message."""
        await self.connection.send(b"\x01\x02\xfe\xff")
        self.assertEqual(await self.remote_connection.recv(), b"\x01\x02\xfe\xff")

    async def test_send_fragmented_text(self):
        """send sends a fragmented text message."""
        await self.connection.send(["😀", "😀"])
        # websockets sends an trailing empty fragment. That's an implementation detail.
        self.assertEqual(
            await alist(self.remote_connection.recv_streaming()),
            ["😀", "😀", ""],
        )

    async def test_send_fragmented_binary(self):
        """send sends a fragmented binary message."""
        await self.connection.send([b"\x01\x02", b"\xfe\xff"])
        # websockets sends an trailing empty fragment. That's an implementation detail.
        self.assertEqual(
            await alist(self.remote_connection.recv_streaming()),
            [b"\x01\x02", b"\xfe\xff", b""],
        )

    async def test_send_async_fragmented_text(self):
        """send sends a fragmented text message asynchronously."""

        async def fragments():
            yield "😀"
            yield "😀"

        await self.connection.send(fragments())
        # websockets sends an trailing empty fragment. That's an implementation detail.
        self.assertEqual(
            await alist(self.remote_connection.recv_streaming()),
            ["😀", "😀", ""],
        )

    async def test_send_async_fragmented_binary(self):
        """send sends a fragmented binary message asynchronously."""

        async def fragments():
            yield b"\x01\x02"
            yield b"\xfe\xff"

        await self.connection.send(fragments())
        # websockets sends an trailing empty fragment. That's an implementation detail.
        self.assertEqual(
            await alist(self.remote_connection.recv_streaming()),
            [b"\x01\x02", b"\xfe\xff", b""],
        )

    async def test_send_connection_closed_ok(self):
        """send raises ConnectionClosedOK after a normal closure."""
        await self.remote_connection.close()
        with self.assertRaises(ConnectionClosedOK):
            await self.connection.send("😀")

    async def test_send_connection_closed_error(self):
        """send raises ConnectionClosedError after an error."""
        await self.remote_connection.close(code=CloseCode.INTERNAL_ERROR)
        with self.assertRaises(ConnectionClosedError):
            await self.connection.send("😀")

    async def test_send_while_send_blocked(self):
        """send waits for a previous call to send to complete."""
        # This test fails if the guard with fragmented_send_waiter is removed
        # from send() in the case when message is an Iterable.
        self.connection.pause_writing()
        asyncio.create_task(self.connection.send(["⏳", "⌛️"]))
        await asyncio.sleep(MS)
        await self.assertFrameSent(
            Frame(Opcode.TEXT, "⏳".encode(), fin=False),
        )

        asyncio.create_task(self.connection.send("✅"))
        await asyncio.sleep(MS)
        await self.assertNoFrameSent()

        self.connection.resume_writing()
        await asyncio.sleep(MS)
        await self.assertFramesSent(
            [
                Frame(Opcode.CONT, "⌛️".encode(), fin=False),
                Frame(Opcode.CONT, b"", fin=True),
                Frame(Opcode.TEXT, "✅".encode()),
            ]
        )

    async def test_send_while_send_async_blocked(self):
        """send waits for a previous call to send to complete."""
        # This test fails if the guard with fragmented_send_waiter is removed
        # from send() in the case when message is an AsyncIterable.
        self.connection.pause_writing()

        async def fragments():
            yield "⏳"
            yield "⌛️"

        asyncio.create_task(self.connection.send(fragments()))
        await asyncio.sleep(MS)
        await self.assertFrameSent(
            Frame(Opcode.TEXT, "⏳".encode(), fin=False),
        )

        asyncio.create_task(self.connection.send("✅"))
        await asyncio.sleep(MS)
        await self.assertNoFrameSent()

        self.connection.resume_writing()
        await asyncio.sleep(MS)
        await self.assertFramesSent(
            [
                Frame(Opcode.CONT, "⌛️".encode(), fin=False),
                Frame(Opcode.CONT, b"", fin=True),
                Frame(Opcode.TEXT, "✅".encode()),
            ]
        )

    async def test_send_during_send_async(self):
        """send waits for a previous call to send to complete."""
        # This test fails if the guard with fragmented_send_waiter is removed
        # from send() in the case when message is an AsyncIterable.
        gate = asyncio.get_running_loop().create_future()

        async def fragments():
            yield "⏳"
            await gate
            yield "⌛️"

        asyncio.create_task(self.connection.send(fragments()))
        await asyncio.sleep(MS)
        await self.assertFrameSent(
            Frame(Opcode.TEXT, "⏳".encode(), fin=False),
        )

        asyncio.create_task(self.connection.send("✅"))
        await asyncio.sleep(MS)
        await self.assertNoFrameSent()

        gate.set_result(None)
        await asyncio.sleep(MS)
        await self.assertFramesSent(
            [
                Frame(Opcode.CONT, "⌛️".encode(), fin=False),
                Frame(Opcode.CONT, b"", fin=True),
                Frame(Opcode.TEXT, "✅".encode()),
            ]
        )

    async def test_send_empty_iterable(self):
        """send does nothing when called with an empty iterable."""
        await self.connection.send([])
        await self.connection.close()
        self.assertEqual(await alist(self.remote_connection), [])

    async def test_send_mixed_iterable(self):
        """send raises TypeError when called with an iterable of inconsistent types."""
        with self.assertRaises(TypeError):
            await self.connection.send(["😀", b"\xfe\xff"])

    async def test_send_unsupported_iterable(self):
        """send raises TypeError when called with an iterable of unsupported type."""
        with self.assertRaises(TypeError):
            await self.connection.send([None])

    async def test_send_empty_async_iterable(self):
        """send does nothing when called with an empty async iterable."""

        async def fragments():
            return
            yield  # pragma: no cover

        await self.connection.send(fragments())
        await self.connection.close()
        self.assertEqual(await alist(self.remote_connection), [])

    async def test_send_mixed_async_iterable(self):
        """send raises TypeError when called with an iterable of inconsistent types."""

        async def fragments():
            yield "😀"
            yield b"\xfe\xff"

        with self.assertRaises(TypeError):
            await self.connection.send(fragments())

    async def test_send_unsupported_async_iterable(self):
        """send raises TypeError when called with an iterable of unsupported type."""

        async def fragments():
            yield None

        with self.assertRaises(TypeError):
            await self.connection.send(fragments())

    async def test_send_dict(self):
        """send raises TypeError when called with a dict."""
        with self.assertRaises(TypeError):
            await self.connection.send({"type": "object"})

    async def test_send_unsupported_type(self):
        """send raises TypeError when called with an unsupported type."""
        with self.assertRaises(TypeError):
            await self.connection.send(None)

    # Test close.

    async def test_close(self):
        """close sends a close frame."""
        await self.connection.close()
        await self.assertFrameSent(Frame(Opcode.CLOSE, b"\x03\xe8"))

    async def test_close_explicit_code_reason(self):
        """close sends a close frame with a given code and reason."""
        await self.connection.close(CloseCode.GOING_AWAY, "bye!")
        await self.assertFrameSent(Frame(Opcode.CLOSE, b"\x03\xe9bye!"))

    async def test_close_waits_for_close_frame(self):
        """close waits for a close frame (then EOF) before returning."""
        async with self.delay_frames_rcvd(MS), self.delay_eof_rcvd(MS):
            await self.connection.close()

        with self.assertRaises(ConnectionClosedOK) as raised:
            await self.connection.recv()

        exc = raised.exception
        self.assertEqual(str(exc), "sent 1000 (OK); then received 1000 (OK)")
        self.assertIsNone(exc.__cause__)

    async def test_close_waits_for_connection_closed(self):
        """close waits for EOF before returning."""
        if self.LOCAL is SERVER:
            self.skipTest("only relevant on the client-side")

        async with self.delay_eof_rcvd(MS):
            await self.connection.close()

        with self.assertRaises(ConnectionClosedOK) as raised:
            await self.connection.recv()

        exc = raised.exception
        self.assertEqual(str(exc), "sent 1000 (OK); then received 1000 (OK)")
        self.assertIsNone(exc.__cause__)

    async def test_close_no_timeout_waits_for_close_frame(self):
        """close without timeout waits for a close frame (then EOF) before returning."""
        self.connection.close_timeout = None

        async with self.delay_frames_rcvd(MS), self.delay_eof_rcvd(MS):
            await self.connection.close()

        with self.assertRaises(ConnectionClosedOK) as raised:
            await self.connection.recv()

        exc = raised.exception
        self.assertEqual(str(exc), "sent 1000 (OK); then received 1000 (OK)")
        self.assertIsNone(exc.__cause__)

    async def test_close_no_timeout_waits_for_connection_closed(self):
        """close without timeout waits for EOF before returning."""
        if self.LOCAL is SERVER:
            self.skipTest("only relevant on the client-side")

        self.connection.close_timeout = None

        async with self.delay_eof_rcvd(MS):
            await self.connection.close()

        with self.assertRaises(ConnectionClosedOK) as raised:
            await self.connection.recv()

        exc = raised.exception
        self.assertEqual(str(exc), "sent 1000 (OK); then received 1000 (OK)")
        self.assertIsNone(exc.__cause__)

    async def test_close_timeout_waiting_for_close_frame(self):
        """close times out if no close frame is received."""
        async with self.drop_eof_rcvd(), self.drop_frames_rcvd():
            await self.connection.close()

        with self.assertRaises(ConnectionClosedError) as raised:
            await self.connection.recv()

        exc = raised.exception
        self.assertEqual(str(exc), "sent 1000 (OK); no close frame received")
        self.assertIsInstance(exc.__cause__, TimeoutError)

    async def test_close_timeout_waiting_for_connection_closed(self):
        """close times out if EOF isn't received."""
        if self.LOCAL is SERVER:
            self.skipTest("only relevant on the client-side")

        async with self.drop_eof_rcvd():
            await self.connection.close()

        with self.assertRaises(ConnectionClosedOK) as raised:
            await self.connection.recv()

        exc = raised.exception
        self.assertEqual(str(exc), "sent 1000 (OK); then received 1000 (OK)")
        # Remove socket.timeout when dropping Python < 3.10.
        self.assertIsInstance(exc.__cause__, (socket.timeout, TimeoutError))

    async def test_close_does_not_wait_for_recv(self):
        # The asyncio implementation has a buffer for incoming messages. Closing
        # the connection discards buffered messages. This is allowed by the RFC:
        # > However, there is no guarantee that the endpoint that has already
        # > sent a Close frame will continue to process data.
        await self.remote_connection.send("😀")
        await self.connection.close()

        with self.assertRaises(ConnectionClosedOK) as raised:
            await self.connection.recv()

        exc = raised.exception
        self.assertEqual(str(exc), "sent 1000 (OK); then received 1000 (OK)")
        self.assertIsNone(exc.__cause__)

    async def test_close_idempotency(self):
        """close does nothing if the connection is already closed."""
        await self.connection.close()
        await self.assertFrameSent(Frame(Opcode.CLOSE, b"\x03\xe8"))

        await self.connection.close()
        await self.assertNoFrameSent()

    async def test_close_during_recv(self):
        """close aborts recv when called concurrently with recv."""
        recv_task = asyncio.create_task(self.connection.recv())
        await asyncio.sleep(MS)
        await self.connection.close()
        with self.assertRaises(ConnectionClosedOK) as raised:
            await recv_task

        exc = raised.exception
        self.assertEqual(str(exc), "sent 1000 (OK); then received 1000 (OK)")
        self.assertIsNone(exc.__cause__)

    async def test_close_during_send(self):
        """close fails the connection when called concurrently with send."""
        gate = asyncio.get_running_loop().create_future()

        async def fragments():
            yield "⏳"
            await gate
            yield "⌛️"

        send_task = asyncio.create_task(self.connection.send(fragments()))
        await asyncio.sleep(MS)

        asyncio.create_task(self.connection.close())
        await asyncio.sleep(MS)

        gate.set_result(None)

        with self.assertRaises(ConnectionClosedError) as raised:
            await send_task

        exc = raised.exception
        self.assertEqual(
            str(exc),
            "sent 1011 (internal error) close during fragmented message; "
            "no close frame received",
        )
        self.assertIsNone(exc.__cause__)

    # Test wait_closed.

    async def test_wait_closed(self):
        """wait_closed waits for the connection to close."""
        wait_closed_task = asyncio.create_task(self.connection.wait_closed())
        await asyncio.sleep(0)  # let the event loop start wait_closed_task
        self.assertFalse(wait_closed_task.done())
        await self.connection.close()
        self.assertTrue(wait_closed_task.done())

    # Test ping.

    @patch("random.getrandbits")
    async def test_ping(self, getrandbits):
        """ping sends a ping frame with a random payload."""
        getrandbits.return_value = 1918987876
        await self.connection.ping()
        getrandbits.assert_called_once_with(32)
        await self.assertFrameSent(Frame(Opcode.PING, b"rand"))

    async def test_ping_explicit_text(self):
        """ping sends a ping frame with a payload provided as text."""
        await self.connection.ping("ping")
        await self.assertFrameSent(Frame(Opcode.PING, b"ping"))

    async def test_ping_explicit_binary(self):
        """ping sends a ping frame with a payload provided as binary."""
        await self.connection.ping(b"ping")
        await self.assertFrameSent(Frame(Opcode.PING, b"ping"))

    async def test_acknowledge_ping(self):
        """ping is acknowledged by a pong with the same payload."""
        async with self.drop_frames_rcvd():  # drop automatic response to ping
            pong_waiter = await self.connection.ping("this")
        await self.remote_connection.pong("this")
        async with asyncio_timeout(MS):
            await pong_waiter

    async def test_acknowledge_ping_non_matching_pong(self):
        """ping isn't acknowledged by a pong with a different payload."""
        async with self.drop_frames_rcvd():  # drop automatic response to ping
            pong_waiter = await self.connection.ping("this")
        await self.remote_connection.pong("that")
        with self.assertRaises(TimeoutError):
            async with asyncio_timeout(MS):
                await pong_waiter

    async def test_acknowledge_previous_ping(self):
        """ping is acknowledged by a pong with the same payload as a later ping."""
        async with self.drop_frames_rcvd():  # drop automatic response to ping
            pong_waiter = await self.connection.ping("this")
            await self.connection.ping("that")
        await self.remote_connection.pong("that")
        async with asyncio_timeout(MS):
            await pong_waiter

    async def test_ping_duplicate_payload(self):
        """ping rejects the same payload until receiving the pong."""
        async with self.drop_frames_rcvd():  # drop automatic response to ping
            pong_waiter = await self.connection.ping("idem")

        with self.assertRaises(RuntimeError) as raised:
            await self.connection.ping("idem")
        self.assertEqual(
            str(raised.exception),
            "already waiting for a pong with the same data",
        )

        await self.remote_connection.pong("idem")
        async with asyncio_timeout(MS):
            await pong_waiter

        await self.connection.ping("idem")  # doesn't raise an exception

    # Test pong.

    async def test_pong(self):
        """pong sends a pong frame."""
        await self.connection.pong()
        await self.assertFrameSent(Frame(Opcode.PONG, b""))

    async def test_pong_explicit_text(self):
        """pong sends a pong frame with a payload provided as text."""
        await self.connection.pong("pong")
        await self.assertFrameSent(Frame(Opcode.PONG, b"pong"))

    async def test_pong_explicit_binary(self):
        """pong sends a pong frame with a payload provided as binary."""
        await self.connection.pong(b"pong")
        await self.assertFrameSent(Frame(Opcode.PONG, b"pong"))

    # Test attributes.

    async def test_id(self):
        """Connection has an id attribute."""
        self.assertIsInstance(self.connection.id, uuid.UUID)

    async def test_logger(self):
        """Connection has a logger attribute."""
        self.assertIsInstance(self.connection.logger, logging.LoggerAdapter)

    @unittest.mock.patch(
        "asyncio.BaseTransport.get_extra_info", return_value=("sock", 1234)
    )
    async def test_local_address(self, get_extra_info):
        """Connection provides a local_address attribute."""
        self.assertEqual(self.connection.local_address, ("sock", 1234))
        get_extra_info.assert_called_with("sockname")

    @unittest.mock.patch(
        "asyncio.BaseTransport.get_extra_info", return_value=("peer", 1234)
    )
    async def test_remote_address(self, get_extra_info):
        """Connection provides a remote_address attribute."""
        self.assertEqual(self.connection.remote_address, ("peer", 1234))
        get_extra_info.assert_called_with("peername")

    async def test_request(self):
        """Connection has a request attribute."""
        self.assertIsNone(self.connection.request)

    async def test_response(self):
        """Connection has a response attribute."""
        self.assertIsNone(self.connection.response)

    async def test_subprotocol(self):
        """Connection has a subprotocol attribute."""
        self.assertIsNone(self.connection.subprotocol)

    # Test reporting of network errors.

    async def test_writing_in_data_received_fails(self):
        """Error when responding to incoming frames is correctly reported."""
        # Inject a fault by shutting down the transport for writing — but not by
        # closing it because that would terminate the connection.
        self.transport.write_eof()
        # Receive a ping. Responding with a pong will fail.
        await self.remote_connection.ping()
        # The connection closed exception reports the injected fault.
        with self.assertRaises(ConnectionClosedError) as raised:
            await self.connection.recv()
        cause = raised.exception.__cause__
        self.assertEqual(str(cause), "Cannot call write() after write_eof()")
        self.assertIsInstance(cause, RuntimeError)

    async def test_writing_in_send_context_fails(self):
        """Error when sending outgoing frame is correctly reported."""
        # Inject a fault by shutting down the transport for writing — but not by
        # closing it because that would terminate the connection.
        self.transport.write_eof()
        # Sending a pong will fail.
        # The connection closed exception reports the injected fault.
        with self.assertRaises(ConnectionClosedError) as raised:
            await self.connection.pong()
        cause = raised.exception.__cause__
        self.assertEqual(str(cause), "Cannot call write() after write_eof()")
        self.assertIsInstance(cause, RuntimeError)

    # Test safety nets — catching all exceptions in case of bugs.

    @patch("websockets.protocol.Protocol.events_received")
    async def test_unexpected_failure_in_data_received(self, events_received):
        """Unexpected internal error in data_received() is correctly reported."""
        # Inject a fault in a random call in data_received().
        # This test is tightly coupled to the implementation.
        events_received.side_effect = AssertionError
        # Receive a message to trigger the fault.
        await self.remote_connection.send("😀")

        with self.assertRaises(ConnectionClosedError) as raised:
            await self.connection.recv()

        exc = raised.exception
        self.assertEqual(str(exc), "no close frame received or sent")
        self.assertIsInstance(exc.__cause__, AssertionError)

    @patch("websockets.protocol.Protocol.send_text")
    async def test_unexpected_failure_in_send_context(self, send_text):
        """Unexpected internal error in send_context() is correctly reported."""
        # Inject a fault in a random call in send_context().
        # This test is tightly coupled to the implementation.
        send_text.side_effect = AssertionError

        # Send a message to trigger the fault.
        # The connection closed exception reports the injected fault.
        with self.assertRaises(ConnectionClosedError) as raised:
            await self.connection.send("😀")

        exc = raised.exception
        self.assertEqual(str(exc), "no close frame received or sent")
        self.assertIsInstance(exc.__cause__, AssertionError)


class ServerConnectionTests(ClientConnectionTests):
    LOCAL = SERVER
    REMOTE = CLIENT
