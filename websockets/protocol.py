"""
The :mod:`websockets.protocol` module handles WebSocket control and data
frames as specified in `sections 4 to 8 of RFC 6455`_.

.. _sections 4 to 8 of RFC 6455: http://tools.ietf.org/html/rfc6455#section-4
"""

__all__ = ['WebSocketCommonProtocol']

import codecs
import collections
import logging
import random
import struct

import asyncio
from asyncio.queues import Queue, QueueEmpty

from .exceptions import InvalidState, PayloadTooBig, WebSocketProtocolError
from .framing import *
from .handshake import *


logger = logging.getLogger(__name__)


class WebSocketCommonProtocol(asyncio.StreamReaderProtocol):
    """
    This class implements common parts of the WebSocket protocol.

    It assumes that the WebSocket connection is established. The handshake is
    managed in subclasses such as
    :class:`~websockets.server.WebSocketServerProtocol` and
    :class:`~websockets.client.WebSocketClientProtocol`.

    It runs a task that stores incoming data frames in a queue and deals with
    control frames automatically. It sends outgoing data frames and performs
    the closing handshake.

    The `host`, `port` and `secure` parameters are simply stored as attributes
    for handlers that need them.

    The `timeout` parameter defines the maximum wait time in seconds for
    completing the closing handshake and, only on the client side, for
    terminating the TCP connection. :meth:`close()` will complete in at most
    this time on the server side and twice this time on the client side.

    The `max_size` parameter enforces the maximum size for incoming messages
    in bytes. The default value is 1MB. ``None`` disables the limit. If a
    message larger than the maximum size is received, :meth:`recv()` will
    return ``None`` and the connection will be closed with status code 1009.

    Once the connection is closed, the status code is available in the
    :attr:`close_code` attribute and the reason in :attr:`close_reason`.
    """

    # There are only two differences between the client-side and the server-
    # side behavior: masking the payload and closing the underlying TCP
    # connection. This class implements the server-side behavior by default.
    # To get the client-side behavior, set is_client = True.

    is_client = False
    state = 'OPEN'

    def __init__(self, *,
                 host=None, port=None, secure=None, timeout=10, max_size=2 ** 20, loop=None):
        self.host = host
        self.port = port
        self.secure = secure

        self.timeout = timeout
        self.max_size = max_size

        super().__init__(asyncio.StreamReader(), self.client_connected, loop)

        self.close_code = None
        self.close_reason = ''

        # Futures tracking steps in the connection's lifecycle.
        self.opening_handshake = asyncio.Future()
        self.closing_handshake = asyncio.Future()
        self.connection_failed = asyncio.Future()
        self.connection_closed = asyncio.Future()

        # Queue of received messages.
        self.messages = Queue()

        # Mapping of ping IDs to waiters, in chronological order.
        self.pings = collections.OrderedDict()

        # Task managing the connection.
        self.worker = asyncio.async(self.run())

        # In a subclass implementing the opening handshake, the state will be
        # CONNECTING at this point.
        if self.state == 'OPEN':
            self.opening_handshake.set_result(True)

    # Public API

    @property
    def open(self):
        """
        This property is ``True`` when the connection is usable.

        It may be used to handle disconnections gracefully.
        """
        return self.state == 'OPEN'

    @asyncio.coroutine
    def close(self, code=1000, reason=''):
        """
        This coroutine performs the closing handshake.

        This is the expected way to terminate a connection on the server side.

        It waits for the other end to complete the handshake. It doesn't do
        anything once the connection is closed.

        It's usually safe to wrap this coroutine in `asyncio.async()` since
        errors during connection termination aren't particularly useful.

        The `code` must be an :class:`int` and the `reason` a :class:`str`.
        """
        if self.state == 'OPEN':
            # 7.1.2. Start the WebSocket Closing Handshake
            self.close_code, self.close_reason = code, reason
            yield from self.write_frame(OP_CLOSE, serialize_close(code, reason))
            # 7.1.3. The WebSocket Closing Handshake is Started
            self.state = 'CLOSING'

        # If the connection doesn't terminate within the timeout, break out of
        # the worker loop.
        try:
            yield from asyncio.wait_for(self.worker, timeout=self.timeout)
        except asyncio.TimeoutError:
            self.worker.cancel()

        # The worker should terminate quickly once it has been cancelled.
        yield from self.worker

    @asyncio.coroutine
    def recv(self):
        """
        This coroutine receives the next message.

        It returns a :class:`str` for a text frame and :class:`bytes` for a
        binary frame.

        When the end of the message stream is reached, or when a protocol
        error occurs, :meth:`recv` returns ``None``, indicating that the
        connection is closed.
        """
        # Return any available message
        try:
            return self.messages.get_nowait()
        except QueueEmpty:
            pass

        # Wait for a message until the connection is closed
        next_message = asyncio.async(self.messages.get())
        done, pending = yield from asyncio.wait(
                [next_message, self.worker],
                return_when=asyncio.FIRST_COMPLETED)
        if next_message in done:
            return next_message.result()
        else:
            next_message.cancel()

    @asyncio.coroutine
    def send(self, data):
        """
        This coroutine sends a message.

        It sends a :class:`str` as a text frame and :class:`bytes` as a binary
        frame.

        It raises a :exc:`TypeError` for other inputs and
        :exc:`InvalidState` once the connection is closed.
        """
        if isinstance(data, str):
            opcode = 1
            data = data.encode('utf-8')
        elif isinstance(data, bytes):
            opcode = 2
        else:
            raise TypeError("data must be bytes or str")
        yield from self.write_frame(opcode, data)

    @asyncio.coroutine
    def ping(self, data=None):
        """
        This coroutine sends a ping.

        It returns a Future which will be completed when the corresponding
        pong is received and which you may ignore if you don't want to wait.

        A ping may serve as a keepalive.
        """
        # Protect against duplicates if a payload is explicitly set.
        if data in self.pings:
            raise ValueError("Already waiting for a pong with the same data")
        # Generate a unique random payload otherwise.
        while data is None or data in self.pings:
            data = struct.pack('!I', random.getrandbits(32))

        self.pings[data] = asyncio.Future()
        yield from self.write_frame(OP_PING, data)
        return self.pings[data]

    @asyncio.coroutine
    def pong(self, data=b''):
        """
        This coroutine sends a pong.

        An unsolicited pong may serve as a unidirectional heartbeat.
        """
        yield from self.write_frame(OP_PONG, data)

    # Private methods - no guarantees.

    @asyncio.coroutine
    def run(self):
        # This coroutine guarantees that the connection is closed at exit.
        yield from self.opening_handshake
        while not self.closing_handshake.done():
            try:
                msg = yield from self.read_message()
                if msg is None:
                    break
                self.messages.put_nowait(msg)
            except asyncio.CancelledError:
                break
            except WebSocketProtocolError:
                yield from self.fail_connection(1002)
            except asyncio.IncompleteReadError:
                yield from self.fail_connection(1006)
            except UnicodeDecodeError:
                yield from self.fail_connection(1007)
            except PayloadTooBig:
                yield from self.fail_connection(1009)
            except Exception:
                yield from self.fail_connection(1011)
                raise
        yield from self.close_connection()

    @asyncio.coroutine
    def read_message(self):
        # Reassemble fragmented messages.
        frame = yield from self.read_data_frame(max_size=self.max_size)
        if frame is None:
            return
        if frame.opcode == OP_TEXT:
            text = True
        elif frame.opcode == OP_BINARY:
            text = False
        else:   # frame.opcode == OP_CONT
            raise WebSocketProtocolError("Unexpected opcode")

        # Shortcut for the common case - no fragmentation
        if frame.fin:
            return frame.data.decode('utf-8') if text else frame.data

        # 5.4. Fragmentation
        chunks = []
        max_size = self.max_size
        if text:
            decoder = codecs.getincrementaldecoder('utf-8')(errors='strict')
            if max_size is None:
                def append(frame):
                    nonlocal chunks
                    chunks.append(decoder.decode(frame.data, frame.fin))
            else:
                def append(frame):
                    nonlocal chunks, max_size
                    chunks.append(decoder.decode(frame.data, frame.fin))
                    max_size -= len(frame.data)
        else:
            if max_size is None:
                def append(frame):
                    nonlocal chunks
                    chunks.append(frame.data)
            else:
                def append(frame):
                    nonlocal chunks, max_size
                    chunks.append(frame.data)
                    max_size -= len(frame.data)
        append(frame)

        while not frame.fin:
            frame = yield from self.read_data_frame(max_size=max_size)
            if frame is None:
                raise WebSocketProtocolError("Incomplete fragmented message")
            if frame.opcode != OP_CONT:
                raise WebSocketProtocolError("Unexpected opcode")
            append(frame)

        return ('' if text else b'').join(chunks)

    @asyncio.coroutine
    def read_data_frame(self, max_size):
        # Deal with control frames automatically and return next data frame.
        # 6.2. Receiving Data
        while True:
            frame = yield from self.read_frame(max_size)
            # 5.5. Control Frames
            if frame.opcode == OP_CLOSE:
                self.close_code, self.close_reason = parse_close(frame.data)
                if self.state != 'CLOSING':
                    # 7.1.3. The WebSocket Closing Handshake is Started
                    self.state = 'CLOSING'
                    yield from self.write_frame(OP_CLOSE, frame.data, 'CLOSING')
                if not self.closing_handshake.done():
                    self.closing_handshake.set_result(True)
                return
            elif frame.opcode == OP_PING:
                # Answer pings.
                yield from self.pong(frame.data)
            elif frame.opcode == OP_PONG:
                # Do not acknowledge pings on unsolicited pongs.
                if frame.data in self.pings:
                    # Acknowledge all pings up to the one matching this pong.
                    ping_id = None
                    while ping_id != frame.data:
                        ping_id, waiter = self.pings.popitem(0)
                        if not waiter.cancelled():
                            waiter.set_result(None)
            # 5.6. Data Frames
            else:
                return frame

    @asyncio.coroutine
    def read_frame(self, max_size):
        is_masked = not self.is_client
        frame = yield from read_frame(self.reader.readexactly, is_masked, max_size=max_size)
        side = 'client' if self.is_client else 'server'
        logger.debug("%s << %s", side, frame)
        return frame

    @asyncio.coroutine
    def write_frame(self, opcode, data=b'', expected_state='OPEN'):
        # This may happen if a user attempts to write on a closed connection.
        if self.state != expected_state:
            raise InvalidState("Cannot write to a WebSocket "
                               "in the {} state".format(self.state))
        frame = Frame(True, opcode, data)
        side = 'client' if self.is_client else 'server'
        logger.debug("%s >> %s", side, frame)
        is_masked = self.is_client
        write_frame(frame, self.writer.write, is_masked)
        try:
            # Handle flow control automatically.
            yield from self.writer.drain()
        except ConnectionResetError:
            # Terminate the connection if the socket died,
            # unless it's already being closed.
            if expected_state != 'CLOSING':
                self.state = 'CLOSING'
                yield from self.fail_connection(1006)

    @asyncio.coroutine
    def close_connection(self):
        # 7.1.1. Close the WebSocket Connection
        if self.state == 'CLOSED':
            return

        # Defensive assertion for protocol compliance.
        if self.state != 'CLOSING':                         # pragma: no cover
            raise InvalidState("Cannot close a WebSocket connection "
                               "in the {} state".format(self.state))

        if self.is_client:
            try:
                yield from asyncio.wait_for(self.connection_closed,
                        timeout=self.timeout)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

            if self.state == 'CLOSED':
                return

        # Attempt to terminate the TCP connection properly.
        # If the socket is already closed, this will crash.
        try:
            if self.writer.can_write_eof():
                self.writer.write_eof()
        except Exception:
            pass

        self.writer.close()

        try:
            yield from asyncio.wait_for(self.connection_closed,
                    timeout=self.timeout)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass

    @asyncio.coroutine
    def fail_connection(self, code=1011, reason=''):
        # Avoid calling fail_connection more than once to minimize
        # the consequences of race conditions between the two sides.
        if self.connection_failed.done():
            # Wait until the other coroutine calls connection_lost.
            yield from self.connection_closed
            return
        else:
            self.connection_failed.set_result(None)

        # Losing the connection usually results in a protocol error.
        # Preserve the original error code in this case.
        if self.close_code != 1006:
            self.close_code, self.close_reason = code, reason
        # 7.1.7. Fail the WebSocket Connection
        logger.info("Failing the WebSocket connection: %d %s", code, reason)
        if self.state == 'OPEN':
            yield from self.write_frame(OP_CLOSE, serialize_close(code, reason))
            self.state = 'CLOSING'
        if not self.closing_handshake.done():
            self.closing_handshake.set_result(False)
        yield from self.close_connection()

    # asyncio StreamReaderProtocol methods

    def client_connected(self, reader, writer):
        self.reader = reader
        self.writer = writer

    def connection_lost(self, exc):
        # 7.1.4. The WebSocket Connection is Closed
        self.state = 'CLOSED'
        if not self.connection_closed.done():
            self.connection_closed.set_result(None)
        if self.close_code is None:
            self.close_code = 1006
        super().connection_lost(exc)
