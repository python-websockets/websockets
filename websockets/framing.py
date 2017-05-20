"""
The :mod:`websockets.framing` module implements data framing as specified in
`section 5 of RFC 6455`_.

It deals with a single frame at a time. Anything that depends on the sequence
of frames is implemented in :mod:`websockets.protocol`.

.. _section 5 of RFC 6455: http://tools.ietf.org/html/rfc6455#section-5

"""

import asyncio
import collections
import io
import random
import struct

from .exceptions import PayloadTooBig, WebSocketProtocolError


__all__ = [
    'DATA_OPCODES', 'CTRL_OPCODES',
    'OP_CONT', 'OP_TEXT', 'OP_BINARY', 'OP_CLOSE', 'OP_PING', 'OP_PONG',
    'Frame', 'parse_close', 'serialize_close'
]

DATA_OPCODES = OP_CONT, OP_TEXT, OP_BINARY = 0x00, 0x01, 0x02
CTRL_OPCODES = OP_CLOSE, OP_PING, OP_PONG = 0x08, 0x09, 0x0a

CLOSE_CODES = {
    1000: "OK",
    1001: "going away",
    1002: "protocol error",
    1003: "unsupported type",
    # 1004: - (reserved)
    # 1005: no status code (internal)
    # 1006: connection closed abnormally (internal)
    1007: "invalid data",
    1008: "policy violation",
    1009: "message too big",
    1010: "extension required",
    1011: "unexpected error",
    # 1015: TLS failure (internal)
}


FrameData = collections.namedtuple(
    'FrameData',
    ['fin', 'opcode', 'data', 'rsv1', 'rsv2', 'rsv3'],
)


class Frame(FrameData):
    """
    WebSocket frame.

    * ``fin`` is the FIN bit
    * ``rsv1`` is the RSV1 bit
    * ``rsv2`` is the RSV2 bit
    * ``rsv3`` is the RSV3 bit
    * ``opcode`` is the opcode
    * ``data`` is the payload data

    Only these fields are needed by higher level code. The MASK bit, payload
    length and masking-key are handled on the fly by :meth:`read` and
    :meth:`write`.

    """
    def __new__(cls, fin, opcode, data, rsv1=False, rsv2=False, rsv3=False):
        return FrameData.__new__(cls, fin, opcode, data, rsv1, rsv2, rsv3)

    @classmethod
    @asyncio.coroutine
    def read(cls, reader, *, mask, max_size=None, extensions=()):
        """
        Read a WebSocket frame and return a :class:`Frame` object.

        ``reader`` is a coroutine taking an integer argument and reading
        exactly this number of bytes, unless the end of file is reached.

        ``mask`` is a :class:`bool` telling whether the frame should be masked
        i.e. whether the read happens on the server side.

        If ``max_size`` is set and the payload exceeds this size in bytes,
        :exc:`~websockets.exceptions.PayloadTooBig` is raised.

        If ``extensions`` is provided, it's a list of classes with an
        ``decode()`` method that transform the frame and return a new frame.
        They are applied in order.

        This function validates the frame before returning it and raises
        :exc:`~websockets.exceptions.WebSocketProtocolError` if it contains
        incorrect values.

        """
        # Read the header
        data = yield from reader(2)
        head1, head2 = struct.unpack('!BB', data)

        # While not Pythonic, this is marginally faster than calling bool().
        fin = True if head1 & 0b10000000 else False
        rsv1 = True if head1 & 0b01000000 else False
        rsv2 = True if head1 & 0b00100000 else False
        rsv3 = True if head1 & 0b00010000 else False
        opcode = head1 & 0b00001111

        if (True if head2 & 0b10000000 else False) != mask:
            raise WebSocketProtocolError("Incorrect masking")

        length = head2 & 0b01111111
        if length == 126:
            data = yield from reader(2)
            length, = struct.unpack('!H', data)
        elif length == 127:
            data = yield from reader(8)
            length, = struct.unpack('!Q', data)
        if max_size is not None and length > max_size:
            raise PayloadTooBig("Payload exceeds limit "
                                "({} > {} bytes)".format(length, max_size))
        if mask:
            mask_bits = yield from reader(4)

        # Read the data
        data = yield from reader(length)
        if mask:
            data = bytes(b ^ mask_bits[i % 4] for i, b in enumerate(data))

        frame = cls(fin, opcode, data, rsv1, rsv2, rsv3)

        frame.check()

        for extension in reversed(extensions):
            frame = extension.decode(frame)

        return frame

    def write(frame, writer, *, mask, extensions=()):
        """
        Write a WebSocket frame.

        ``frame`` is the :class:`Frame` object to write.

        ``writer`` is a function accepting bytes.

        ``mask`` is a :class:`bool` telling whether the frame should be masked
        i.e. whether the write happens on the client side.

        If ``extensions`` is provided, it's a list of classes with an
        ``encode()`` method that transform the frame and return a new frame.
        They are applied in order.

        This function validates the frame before sending it and raises
        :exc:`~websockets.exceptions.WebSocketProtocolError` if it contains
        incorrect values.

        """

        # The first parameter is called `frame` rather than `self`,
        # but it's the instance of class to which this method is bound.

        for extension in extensions:
            frame = extension.encode(frame)

        frame.check()

        output = io.BytesIO()

        # Prepare the header
        head1 = (
            (0b10000000 if frame.fin else 0) |
            (0b01000000 if frame.rsv1 else 0) |
            (0b00100000 if frame.rsv2 else 0) |
            (0b00010000 if frame.rsv3 else 0) |
            frame.opcode
        )

        head2 = 0b10000000 if mask else 0

        length = len(frame.data)
        if length < 126:
            output.write(struct.pack('!BB', head1, head2 | length))
        elif length < 65536:
            output.write(struct.pack('!BBH', head1, head2 | 126, length))
        else:
            output.write(struct.pack('!BBQ', head1, head2 | 127, length))

        if mask:
            mask_bits = struct.pack('!I', random.getrandbits(32))
            output.write(mask_bits)

        # Prepare the data
        if mask:
            data = bytes(
                byte ^ mask_bits[index % 4]
                for index, byte in enumerate(frame.data)
            )
        else:
            data = frame.data
        output.write(data)

        # Send the frame
        writer(output.getvalue())

    def check(frame):
        """
        Raise :exc:`~websockets.exceptions.WebSocketProtocolError` if the frame
        contains incorrect values.

        """

        # The first parameter is called `frame` rather than `self`,
        # but it's the instance of class to which this method is bound.

        if frame.rsv1 or frame.rsv2 or frame.rsv3:
            raise WebSocketProtocolError("Reserved bits must be 0")

        if frame.opcode in DATA_OPCODES:
            return
        elif frame.opcode in CTRL_OPCODES:
            if len(frame.data) > 125:
                raise WebSocketProtocolError("Control frame too long")
            if not frame.fin:
                raise WebSocketProtocolError("Fragmented control frame")
        else:
            raise WebSocketProtocolError("Invalid opcode")


def parse_close(data):
    """
    Parse the data in a close frame.

    Return ``(code, reason)`` when ``code`` is an :class:`int` and ``reason``
    a :class:`str`.

    Raise :exc:`~websockets.exceptions.WebSocketProtocolError` or
    :exc:`UnicodeDecodeError` if the data is invalid.

    """
    length = len(data)
    if length == 0:
        return 1005, ''
    elif length >= 2:
        code, = struct.unpack('!H', data[:2])
        check_close(code)
        reason = data[2:].decode('utf-8')
        return code, reason
    else:
        raise WebSocketProtocolError("Close frame too short")


def serialize_close(code, reason):
    """
    Serialize the data for a close frame.

    This is the reverse of :func:`parse_close`.

    """
    check_close(code)
    return struct.pack('!H', code) + reason.encode('utf-8')


def check_close(code):
    """
    Check the close code for a close frame.

    """
    if not (code in CLOSE_CODES or 3000 <= code < 5000):
        raise WebSocketProtocolError("Invalid status code")
