"""
The :mod:`websockets.framing` module implements data framing as specified in
`sections 5 to 8 of RFC 6455`_.

.. _sections 5 to 8 of RFC 6455: http://tools.ietf.org/html/rfc6455#section-4


"""

__all__ = ['WebSocketProtocol']

import collections
import io
import random
import struct
import warnings

import tulip


OP_CONTINUATION = 0
OP_TEXT = 1
OP_BINARY = 2
OP_CLOSE = 8
OP_PING = 9
OP_PONG = 10


Frame = collections.namedtuple('Frame', ('fin', 'opcode', 'data'))


class WebSocketFraming:
    """
    This class is a generic WebSocket frames implementation.

    It assumes that the opening handshake and the upgrade from HTTP have been
    completed. It deals with with sending and receiving data, and with the
    closing handshake.

    It implements the server side behavior by default. To obtain the client
    side behavior, instantiate it with `is_client=True`.
    """

    def __init__(self, reader, writer, is_client=False):
        """
        Create a WebSocket frames handler.

        `reader` is a coroutine that takes an integer argument, and reads
        exactly this number of bytes. `writer` is a non-blocking function.
        """
        self.reader = reader
        self.writer = writer
        self.is_client = is_client          # This is redundant but avoids
        self.is_server = not is_client      # confusing negations.
        self.local_closed = False
        self.remote_closed = False

    @tulip.coroutine
    def recv(self):
        """
        This coroutine receives the next message.

        It returns a :class:`str` for a text frame and :class:`bytes` for a
        binary frame.

        It raises :exc:`IOError` once the connection is closed.
        """
        # RFC 6455 - 5.4. Fragmentation
        frame = yield from self.read_data_frame()
        if frame is None:
            return
        if frame.opcode == OP_TEXT:
            text = True
        elif frame.opcode == OP_BINARY:
            text = False
        else:
            raise ValueError("Unexpected opcode")
        data = [frame.data]
        while not frame.fin:
            frame = yield from self.read_data_frame()
            if frame.opcode != OP_CONTINUATION:
                raise ValueError("Unexpected opcode")
            data.append(frame.data)
        data = b''.join(data)
        return data.decode('utf-8') if text else data

    def send(self, data):
        """
        This function sends a message.

        It sends a :class:`str` as a text frame and :class:`bytes` as a binary
        frame.

        It raises a :exc:`TypeError` for other inputs and :exc:`IOError` once
        the connection is closed.
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
    def close(self, data=b''):
        """
        This coroutine performs the closing handshake.

        It waits for the other end to complete the handshake. It doesn't do
        anything once the connection is closed.

        The underlying connection must be closed once this coroutine returns.

        This is the expected way to terminate a connection on the server side.

        Status codes aren't implemented, but they can be passed in `data`.
        """
        if self.is_client:
            warnings.warn("Clients SHOULD NOT close the WebSocket connection "
                          "arbitrarily (RFC 6455, 7.3).")
        if not self.local_closed:
            self.write_frame(OP_CLOSE, data)
            self.local_closed = True
            # Discard unprocessed messages until we get the other end's close.
            yield from self.wait_close()

    @tulip.coroutine
    def wait_close(self):
        """
        This coroutine waits for the closing handshake.

        It doesn't do anything once the connection is closed.

        This is the expected way to terminate a connection on the client side.
        """
        while (yield from self.recv()) is not None:
            pass

    def ping(self, data=b''):
        """
        Send a ping.

        A ping may serve as a keepalive.
        """
        self.write_frame(OP_PING, data)

    def pong(self, data=b''):
        """
        Send a pong.

        An unsolicited pong may serve as a unidirectional heartbeat.
        """
        self.write_frame(OP_PONG, data)

    @tulip.coroutine
    def read_data_frame(self):
        # RFC 6455 - 6.2. Receiving Data
        while not self.remote_closed:
            frame = yield from self.read_frame()
            # RFC 6455 - 5.5. Control Frames
            if frame.opcode & 0b1000:
                if frame.opcode == OP_CLOSE:
                    self.remote_closed = True
                    self.close()
                elif frame.opcode == OP_PING:
                    self.pong(frame.data)
                elif frame.opcode == OP_PONG:
                    pass                    # unsolicited Pong
                else:
                    raise ValueError("Unexpected opcode")
            # RFC 6455 - 5.6. Data Frames
            else:
                return frame

    @tulip.coroutine
    def read_frame(self):
        if self.remote_closed:
            raise IOError("Cannot read from a closed WebSocket")

        # Read the header
        data = yield from self.reader(2)
        head1, head2 = struct.unpack('!BB', data)
        fin = bool(head1 & 0b10000000)
        assert not head1 & 0b01110000, "reserved bits must be 0"
        opcode = head1 & 0b00001111
        assert bool(head2 & 0b10000000) == self.is_server, "invalid masking"
        length = head2 & 0b01111111
        if length == 126:
            data = yield from self.reader(2)
            length, = struct.unpack('!H', data)
        elif length == 127:
            data = yield from self.reader(8)
            length, = struct.unpack('!Q', data)
        if self.is_server:
            mask = yield from self.reader(4)

        # Read the data
        data = yield from self.reader(length)
        if self.is_server:
            data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))

        return Frame(fin, opcode, data)

    def write_frame(self, opcode, data=b''):
        if self.local_closed:
            raise IOError("Cannot write to a closed WebSocket")

        # Write the header
        header = io.BytesIO()
        header.write(struct.pack('!B', 0b10000000 | opcode))
        if self.is_server:
            mask_bit = 0b00000000
        else:
            mask_bit = 0b10000000
            mask = struct.pack('!I', random.getrandbits(32))
        length = len(data)
        if length < 0x7e:
            header.write(struct.pack('!B', mask_bit | length))
        elif length < 0x10000:
            header.write(struct.pack('!BH', mask_bit | 126, length))
        else:
            header.write(struct.pack('!BQ', mask_bit | 127, length))
        if self.is_client:
            header.write(mask)
        self.writer(header.getvalue())

        # Write the data
        if self.is_client:
            data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        self.writer(data)


class WebSocketProtocol(WebSocketFraming, tulip.Protocol):
    """
    This class implements WebSocket framing as a Tulip protocol.

    It assumes that the opening handshake and the upgrade from HTTP have been
    completed. It deals with with sending and receiving data, and with the
    closing handshake.

    It implements the server side behavior by default. To obtain the client
    side behavior, instantiate it with `is_client=True`.
    """

    def __init__(self, is_client=False):
        super().__init__(None, None, is_client)

    def connection_made(self, transport):
        self.transport = transport
        self.stream = tulip.StreamReader()
        self.reader = self.stream.readexactly
        self.writer = self.transport.write

    def data_received(self, data):
        self.stream.feed_data(data)

    def eof_received(self):
        self.stream.feed_eof()

    def connection_lost(self, exc):
        pass

    @tulip.coroutine
    def close(self, data=b''):
        """
        This coroutine performs the closing handshake.

        It waits for the other end to complete the handshake. It doesn't do
        anything once the connection is closed.

        This is the expected way to terminate a connection on the server side.

        Status codes aren't implemented, but they can be passed in `data`.
        """
        yield from super().close(data)
        self.transport.close()
