"""
The :mod:`websockets.protocols` module implements the rules of the WebSocket
protocol as specified in `sections 4 to 8 of RFC 6455`_.

.. _sections 4 to 8 of RFC 6455: http://tools.ietf.org/html/rfc6455#section-4
"""

__all__ = ['WebSocketCommonProtocol']

import codecs
import collections
import logging
import random
import struct

import tulip

from .exceptions import InvalidHandshake, InvalidState, WebSocketProtocolError
from .framing import *
from .handshake import *
from .http import read_request, read_response, USER_AGENT


logger = logging.getLogger(__name__)


class WebSocketCommonProtocol(tulip.Protocol):
    """
    This class implements common parts of the WebSocket protocol.

    It assumes that the WebSocket connection is established. It runs a task
    that stores incoming data frames in a queue and deals with control frames
    automatically. It sends outgoing data frames and performs with the closing
    handshake.

    The `timeout` parameter defines the maximum wait time in seconds for
    completing the closing handshake and for terminating the TCP connection.
    :meth:`close()` will complete in at most twice this time.

    Once the connection is closed, the status code is available in the
    :attr:`close_code` attribute and the reason in :attr:`close_reason`. If
    you need to wait until the connection is closed, you can yield from
    :attr:`close_waiter`.

    There are only two differences between the client-side and the server-side
    behavior: masking the payload and closing the underlying TCP connection.
    This class implements the server-side behavior by default. To get the
    client-side behavior, set the class attribute ``is_client`` to ``True``.
    """

    is_client = False
    state = 'OPEN'

    def __init__(self, timeout=10):
        self.timeout = timeout

        self.close_code = None
        self.close_reason = ''
        self.close_waiter = tulip.Future()

        self.opening_handshake = tulip.Future()
        self.closing_handshake = tulip.Future()

        # I'm not satisfied with the current API of tulip.parsers because it
        # goes overboard with generators, eg. `out, buf = yield`. I doubt
        # it'll end up in the standard library as is. For the time being I'll
        # just use a DataBuffer to store received messages.
        self.messages = tulip.DataBuffer()
        # Mapping of ping IDs to waiters, in chronological order.
        self.pings = collections.OrderedDict()

        self.run()

        # In a subclass implementing the opening handshake, the state will be
        # CONNECTING at this point.
        if self.state == 'OPEN':
            self.opening_handshake.set_result(True)

    # Public API

    @property
    def open(self):
        """
        This property is ``True`` when the connection is usable.

        It can be used to write loops on the server side and handle
        disconnections gracefully::

            while ws.open:
                # ...
        """
        return self.state == 'OPEN'

    @tulip.coroutine
    def recv(self):
        """
        This coroutine receives the next message.

        It returns a :class:`str` for a text frame and :class:`bytes` for a
        binary frame.

        When the end of the message stream is reached, or when a protocol
        error occurs, :meth:`recv` returns ``None``, indicating that the
        connection is closed.

        It's forbidden to call :meth:`recv` from two coroutines in parallel.
        If this happens, the second call wil raise a :exc:`RuntimeError`.
        """
        # Using an internal API isn't great, but it beats catching
        # AssertionError and re-raising RuntimeError.
        if self.messages._waiter is not None:
            raise RuntimeError(
                    "Another coroutine is already yielding from recv()")
        return (yield from self.messages.read())

    def send(self, data):
        """
        This function sends a message.

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
        self.write_frame(opcode, data)

    @tulip.task
    def close(self, code=1000, reason=''):
        """
        This task performs the closing handshake.

        This is the expected way to terminate a connection on the server side.

        It waits for the other end to complete the handshake. It doesn't do
        anything once the connection is closed.

        The `code` must be an :class:`int` and the `reason` a :class:`str`.
        """
        if self.state == 'OPEN':
            # 7.1.2. Start the WebSocket Closing Handshake
            self.close_code, self.close_reason = code, reason
            self.write_frame(OP_CLOSE, serialize_close(code, reason))
            # 7.1.3. The WebSocket Closing Handshake is Started
            self.state = 'CLOSING'

        yield from tulip.wait([self.closing_handshake], timeout=self.timeout)
        yield from tulip.wait([self.close_waiter], timeout=self.timeout)

        if self.state != 'CLOSED':
            self.transport.close()

    @tulip.task
    def ping(self, data=None):
        """
        This coroutine sends a ping and waits for the corresponding pong.

        A ping may serve as a keepalive.

        Since it's implemented as a task, you can simply call it as a function
        if you don't need to wait.
        """
        # Protect against duplicates if a payload is explicitly set.
        if data in self.pings:
            raise ValueError("Already waiting for a pong with the same data")
        # Generate a unique random payload otherwise.
        while data is None or data in self.pings:
            data = struct.pack('!I', random.getrandbits(32))

        self.pings[data] = tulip.Future()
        self.write_frame(OP_PING, data)
        yield from self.pings[data]

    def pong(self, data=b''):
        """
        This function sends a pong.

        An unsolicited pong may serve as a unidirectional heartbeat.
        """
        self.write_frame(OP_PONG, data)

    # Semi-public API - for advanced use, but it should be stable.

    def handle_message(self, msg):
        self.messages.feed_data(msg)

    def handle_eof(self):
        self.messages.feed_eof()

    def handle_exception(self, exc):
        self.messages.set_exception(exc)

    # Private methods - no guarantees.

    @tulip.task
    def run(self):
        yield from self.opening_handshake
        while not self.closing_handshake.done():
            try:
                msg = yield from self.read_message()
                if msg is None:
                    break
                self.handle_message(msg)
            except WebSocketProtocolError:
                yield from self.fail_connection(1002)
            except UnicodeDecodeError:
                yield from self.fail_connection(1007)
            except Exception as exc:
                yield from self.fail_connection(1011)   # bug in coverage.py?
                self.handle_exception(exc)              # pragma: no branch
        self.handle_eof()

    @tulip.coroutine
    def read_message(self):
        # Reassemble fragmented messages.
        frame = yield from self.read_data_frame()
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
        if text:
            decoder = codecs.getincrementaldecoder('utf-8')(errors='strict')
            append = lambda f: chunks.append(decoder.decode(f.data, f.fin))
        else:
            append = lambda f: chunks.append(f.data)
        append(frame)

        while not frame.fin:
            frame = yield from self.read_data_frame()
            if frame is None:
                raise WebSocketProtocolError("Incomplete fragmented message")
            if frame.opcode != OP_CONT:
                raise WebSocketProtocolError("Unexpected opcode")
            append(frame)

        return ('' if text else b'').join(chunks)

    @tulip.coroutine
    def read_data_frame(self):
        # Deal with control frames automatically and return next data frame.
        # 6.2. Receiving Data
        while True:
            frame = yield from self.read_frame()
            # 5.5. Control Frames
            if frame.opcode == OP_CLOSE:
                self.close_code, self.close_reason = parse_close(frame.data)
                if self.state != 'CLOSING':
                    # 7.1.3. The WebSocket Closing Handshake is Started
                    self.state = 'CLOSING'
                    self.write_frame(OP_CLOSE, frame.data, 'CLOSING')
                self.closing_handshake.set_result(True)
                yield from self.close_connection()
                return
            elif frame.opcode == OP_PING:
                # Answer pings.
                self.pong(frame.data)
            elif frame.opcode == OP_PONG:
                # Do not acknowledge pings on unsolicited pongs.
                if frame.data in self.pings:
                    # Acknowledge all pings up to the one matching this pong.
                    ping_id = None
                    while ping_id != frame.data:
                        ping_id, waiter = self.pings.popitem(0)
                        waiter.set_result(None)
            # 5.6. Data Frames
            else:
                return frame

    @tulip.coroutine
    def read_frame(self):
        is_masked = not self.is_client
        frame = yield from read_frame(self.stream.readexactly, is_masked)
        side = 'client' if self.is_client else 'server'
        logger.debug("%s << %s", side, frame)
        return frame

    def write_frame(self, opcode, data=b'', expected_state='OPEN'):
        # This may happen if a user attempts to write on a closed connection.
        if self.state != expected_state:
            raise InvalidState("Cannot write to a WebSocket "
                               "in the {} state".format(self.state))
        frame = Frame(True, opcode, data)
        side = 'client' if self.is_client else 'server'
        logger.debug("%s >> %s", side, frame)
        is_masked = self.is_client
        write_frame(frame, self.transport.write, is_masked)

    @tulip.coroutine
    def close_connection(self):
        # 7.1.1. Close the WebSocket Connection
        if self.state == 'CLOSED':
            return

        # Defensive assertion for protocol compliance.
        if self.state != 'CLOSING':                         # pragma: no cover
            raise InvalidState("Cannot close a WebSocket connection "
                               "in the {} state".format(self.state))

        if self.is_client:
            assert self.conn_lost_alarm is None
            self.conn_lost_alarm = tulip.Future(timeout=self.timeout)
            try:
                yield from self.conn_lost_alarm
            except tulip.CancelledError:
                pass
            finally:
                self.conn_lost_alarm = None
            if self.state != 'CLOSED':
                self.transport.close()
        else:
            self.transport.close()

    @tulip.coroutine
    def fail_connection(self, code=1011, reason=''):
        # Losing the connection usually results in a protocol error.
        # Preserve the original error code in this case.
        if self.close_code != 1006:
            self.close_code, self.close_reason = code, reason
        # 7.1.7. Fail the WebSocket Connection
        logger.info("Failing the WebSocket connection: %d %s", code, reason)
        if self.state == 'OPEN':
            self.write_frame(OP_CLOSE, serialize_close(code, reason))
            self.state = 'CLOSING'
        if not self.closing_handshake.done():
            self.closing_handshake.set_result(False)
        yield from self.close_connection()

    # Tulip Protocol methods

    def connection_made(self, transport):
        self.transport = transport
        self.stream = tulip.StreamReader()
        self.conn_lost_alarm = None

    def data_received(self, data):
        self.stream.feed_data(data)

    def eof_received(self):
        self.stream.feed_eof()
        self.transport.close()

    def connection_lost(self, exc):
        # 7.1.4. The WebSocket Connection is Closed
        self.close_waiter.set_result(None)
        self.state = 'CLOSED'
        if self.conn_lost_alarm and not self.conn_lost_alarm.done():
            self.conn_lost_alarm.set_result(None)
        if self.close_code is None:
            self.close_code = 1006
