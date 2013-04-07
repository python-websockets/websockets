"""
The :mod:`websockets.framing` module implements data framing as specified in
`sections 5 to 8 of RFC 6455`_.

.. _sections 5 to 8 of RFC 6455: http://tools.ietf.org/html/rfc6455#section-4


"""

__all__ = ['WebSocketProtocol', 'InvalidOperation']

import codecs
import collections
import io
import logging
import random
import struct
import warnings

import tulip


logger = logging.getLogger(__name__)

OP_CONTINUATION = 0
OP_TEXT = 1
OP_BINARY = 2
OP_CLOSE = 8
OP_PING = 9
OP_PONG = 10

CLOSE_CODES = {
    1000: "OK",
    1001: "going away",
    1002: "protocol error",
    1003: "unsupported type",
    # 1004: - (reserved)
    # 1005: no status code (internal)
    # 1006: connection closed (internal)
    1007: "invalid data",
    1008: "policy violation",
    1009: "message too big",
    1010: "extension required",
    1011: "unexpected error",
    # 1015: TLS failure (internal)
}


class InvalidOperation(Exception):
    """Exception raised when attempting an illegal operation."""


class WebSocketProtocolError(Exception):
    # Internal exception raised when the other end breaks the protocol.
    # It's private because it shouldn't leak outside of WebSocketProtocol.
    pass


Frame = collections.namedtuple('Frame', ('fin', 'opcode', 'data'))


class WebSocketProtocol(tulip.Protocol):
    """
    This class implements WebSocket framing as a Tulip Protocol.

    It assumes that the WebSocket connection is established. It deals with
    with sending and receiving data, and with the closing handshake. Once the
    connection is closed, the status code is available in the
    :attr:`close_code` attribute, and the reason in :attr:`close_reason`.

    It implements the server side behavior by default. To obtain the client
    side behavior, instantiate it with `is_client=True`.

    The `timeout` parameter is used when closing the connection.
    """
    state = 'OPEN'

    def __init__(self, is_client=False, timeout=10):
        self.is_client = is_client          # This is redundant but avoids
        self.is_server = not is_client      # confusing negations.
        self.timeout = timeout
        self.close_code = None
        self.close_reason = ''

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

    # Public API

    @tulip.coroutine
    def recv(self):
        """
        This coroutine receives the next message.

        It returns a :class:`str` for a text frame and :class:`bytes` for a
        binary frame.

        It raises :exc:`InvalidOperation` when the connection is closed.
        """
        try:
            return (yield from self.read_message())
        except WebSocketProtocolError:
            self.fail_connection(1002)
        except UnicodeDecodeError:
            self.fail_connection(1007)
        except Exception:
            try:
                self.fail_connection(1011)
            finally:
                raise

    def send(self, data):
        """
        This function sends a message.

        It sends a :class:`str` as a text frame and :class:`bytes` as a binary
        frame.

        It raises a :exc:`TypeError` for other inputs and
        :exc:`InvalidOperation` when the connection is closed.
        """
        if isinstance(data, str):
            opcode = 1
            data = data.encode('utf-8')
        elif isinstance(data, bytes):
            opcode = 2
        else:
            raise TypeError("data must be bytes or str")
        self.write_frame(opcode, data)

    @tulip.coroutine
    def close(self, code=1000, reason=''):
        """
        This coroutine performs the closing handshake.

        It waits for the other end to complete the handshake. It doesn't do
        anything once the connection is closed.

        This is the expected way to terminate a connection on the server side.

        The `code` must be an :class:`int` and the `reason` a :class:`str`.
        """
        if self.state == 'OPEN':
            # 7.1.2. Start the WebSocket Closing Handshake
            self.write_close_frame(code, reason)
            # 7.1.3. The WebSocket Closing Handshake is Started
            self.state = 'CLOSING'
            # Discard frames until we get the other end's close.
            try:
                yield from self.read_close_frame()
            except WebSocketProtocolError:
                self.fail_connection(1002)
        yield from self.close_connection()

    @tulip.coroutine
    def wait_close(self):
        """
        This coroutine waits for the closing handshake.

        It doesn't do anything once the connection is closed.

        This is the expected way to terminate a connection on the client side.
        """
        try:
            while self.state == 'OPEN':
                if (yield from self.read_data_frame()) is None:
                    break
        except WebSocketProtocolError:
            self.fail_connection()

    def ping(self, data=b''):
        """
        This function sends a ping.

        A ping may serve as a keepalive.
        """
        self.write_frame(OP_PING, data)

    def pong(self, data=b''):
        """
        This function sends a pong.

        An unsolicited pong may serve as a unidirectional heartbeat.
        """
        self.write_frame(OP_PONG, data)

    # Private methods

    @tulip.coroutine
    def read_message(self):
        # This coroutine reassembles fragmented messages
        frame = yield from self.read_data_frame()
        if frame is None:
            return
        if frame.opcode == OP_TEXT:
            text = True
        elif frame.opcode == OP_BINARY:
            text = False
        else:   # frame.opcode == OP_CONTINUATION
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
                return
            if frame.opcode != OP_CONTINUATION:
                raise WebSocketProtocolError("Unexpected opcode")
            append(frame)

        return ('' if text else b'').join(chunks)

    @tulip.coroutine
    def read_data_frame(self):
        # This coroutine deals with control frames automatically. It returns
        # the next data frame when the connection is open and None otherwise.

        # 6.2. Receiving Data
        while self.state == 'OPEN':
            frame = yield from self.read_frame()
            # 5.5. Control Frames
            if frame.opcode & 0b1000:
                if len(frame.data) > 125:
                    raise WebSocketProtocolError("Control frame too long")
                if not frame.fin:
                    raise WebSocketProtocolError("Fragmented control frame")
                # 5.5.1. Close
                if frame.opcode == OP_CLOSE:
                    if frame.data:
                        if len(frame.data) < 2:
                            raise WebSocketProtocolError("Close frame too short")
                        code, = struct.unpack('!H', frame.data[:2])
                        if not (code in CLOSE_CODES or 3000 <= code < 5000):
                            raise WebSocketProtocolError("Invalid status code")
                        self.close_code = code
                        self.close_reason = frame.data[2:].decode('utf-8')
                    else:
                        self.close_code = 1005
                    # If the other side initiates the closing handshake, and
                    # this side didn't initiate it during the `yield`, respond
                    # and close the connection.
                    if self.state == 'OPEN':
                        # 7.1.3. The WebSocket Closing Handshake is Started
                        self.state = 'CLOSING'
                        self.write_frame(OP_CLOSE, frame.data, 'CLOSING')
                        yield from self.close_connection()
                        return None
                elif frame.opcode == OP_PING:
                    self.pong(frame.data)
                elif frame.opcode == OP_PONG:
                    pass                    # unsolicited Pong
                else:
                    raise WebSocketProtocolError("Unexpected opcode")
            # 5.6. Data Frames
            elif frame.opcode in (OP_CONTINUATION, OP_TEXT, OP_BINARY):
                return frame
            else:
                raise WebSocketProtocolError("Unexpected opcode")

    @tulip.coroutine
    def read_frame(self, expected_state='OPEN'):
        # This coroutine reads a single frame.

        if self.state != expected_state:
            raise InvalidOperation("Cannot read from a WebSocket "
                                   "in the {} state".format(self.state))

        # Read the header
        data = yield from self.read_bytes(2)
        head1, head2 = struct.unpack('!BB', data)
        fin = bool(head1 & 0b10000000)
        if head1 & 0b01110000:
            raise WebSocketProtocolError("Reserved bits must be 0")
        opcode = head1 & 0b00001111
        if bool(head2 & 0b10000000) != self.is_server:
            raise WebSocketProtocolError("Incorrect masking")
        length = head2 & 0b01111111
        if length == 126:
            data = yield from self.read_bytes(2)
            length, = struct.unpack('!H', data)
        elif length == 127:
            data = yield from self.read_bytes(8)
            length, = struct.unpack('!Q', data)
        if self.is_server:
            mask = yield from self.read_bytes(4)

        # Read the data
        data = yield from self.read_bytes(length)
        if self.is_server:
            data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))

        frame = Frame(fin, opcode, data)
        logger.debug("< %s", frame)
        return frame

    @tulip.coroutine
    def read_bytes(self, n):
        data = yield from self.stream.readexactly(n)
        if len(data) != n:
            raise WebSocketProtocolError("Unexpected EOF")
        return data

    def write_close_frame(self, code=1000, reason=''):
        self.close_code = code
        self.close_reason = reason
        data = struct.pack('!H', code) + reason.encode('utf-8')
        self.write_frame(OP_CLOSE, data)

    def write_frame(self, opcode, data=b'', expected_state='OPEN'):
        if self.state != expected_state:
            raise InvalidOperation("Cannot write to a WebSocket "
                                   "in the {} state".format(self.state))

        logger.debug("> %s", Frame(False, opcode, data))

        # Write the header
        header = io.BytesIO()
        header.write(struct.pack('!B', 0b10000000 | opcode))
        if self.is_client:
            mask_bit = 0b10000000
            mask = struct.pack('!I', random.getrandbits(32))
        else:
            mask_bit = 0b00000000
        length = len(data)
        if length < 0x7e:
            header.write(struct.pack('!B', mask_bit | length))
        elif length < 0x10000:
            header.write(struct.pack('!BH', mask_bit | 126, length))
        else:
            header.write(struct.pack('!BQ', mask_bit | 127, length))
        if self.is_client:
            header.write(mask)
        self.transport.write(header.getvalue())

        # Write the data
        if self.is_client:
            data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        self.transport.write(data)

    @tulip.coroutine
    def read_close_frame(self):
        # This coroutine discards frames until it receives a Close frame.
        self.alarm = tulip.Future(timeout=self.timeout)
        try:
            while self.state == 'CLOSING':
                frame = tulip.Task(self.read_frame('CLOSING'))
                yield from tulip.wait([frame, self.alarm],
                                      return_when=tulip.FIRST_COMPLETED)
                if frame.done() and frame.result().opcode == OP_CLOSE:
                    return True
                if self.alarm.done():
                    return False
        finally:
            self.alarm = None

    @tulip.coroutine
    def close_connection(self):
        if self.state == 'CLOSED':
            return

        if self.state != 'CLOSING':
            raise InvalidOperation("Cannot close a WebSocket connection "
                                   "in the {} state".format(self.state))

        # 7.1.1. Close the WebSocket Connection
        if self.is_server:
            self.transport.close()
        else:
            self.alarm = tulip.Future(timeout=self.timeout)
            try:
                yield from tulip.wait([self.alarm])
            finally:
                self.alarm = None
            if self.state != 'CLOSED':
                self.transport.close()

    def fail_connection(self, code=1011, reason=''):
        # 7.1.7. Fail the WebSocket Connection
        if self.state == 'OPEN':
            self.write_close_frame(code, reason)
            self.state = 'CLOSING'
        self.transport.close()

    # Tulip Protocol methods

    def connection_made(self, transport):
        self.transport = transport
        self.stream = tulip.StreamReader()
        self.alarm = None

    def data_received(self, data):
        self.stream.feed_data(data)

    def eof_received(self):
        self.stream.feed_eof()
        self.transport.close()

    def connection_lost(self, exc):
        # 7.1.4. The WebSocket Connection is Closed
        self.state = 'CLOSED'
        if self.alarm is not None:
            self.alarm.set_result(None)
        if self.close_code is None:
            self.close_code = 1006
