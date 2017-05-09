import zlib

from .framing import CTRL_OPCODES, OP_CONT


__all__ = ['PerMessageDeflate']


_EMPTY_UNCOMPRESSED_BLOCK = b'\x00\x00\xff\xff'


class PerMessageDeflate:
    """
    Compression Extensions for WebSocket (`RFC 7692`_).

    .. _RFC 7692: http://tools.ietf.org/html/rfc7692

    """

    # This class implements the server-side behavior by default.
    # To get the client-side behavior, set is_client = True.
    is_client = False

    def __init__(self):
        # Currently there's no way to customize these parameters.
        self.server_no_context_takeover = False
        self.client_no_context_takeover = False
        self.server_max_window_bits = 15
        self.client_max_window_bits = 15
        # Internal state.
        self.decoder = zlib.decompressobj(
            wbits=-(
                self.server_max_window_bits
                if self.is_client else
                self.client_max_window_bits
            ),
        )
        self.encoder = zlib.compressobj(
            wbits=-(
                self.client_max_window_bits
                if self.is_client else
                self.server_max_window_bits
            ),
        )
        self.decode_cont_data = False
        self.encode_cont_data = False

    def name(self):
        return 'permessage-deflate'

    def decode(self, frame):
        """
        Decode an incoming frame.

        """
        # Skip control frames.
        if frame.opcode in CTRL_OPCODES:
            return frame
        # Handle continuation data frames:
        # - skip if the initial data frame wasn't encoded
        # - reset "decode continuation data" flag if it's a final frame
        elif frame.opcode == OP_CONT:
            if not self.decode_cont_data:
                return frame
            if frame.fin:
                self.decode_cont_data = False
        # Handle text and binary data frames:
        # - skip if the frame isn't encoded
        # - set "decode continuation data" flag if it's a non-final frame
        else:
            if not frame.rsv1:
                return frame
            if not frame.fin:   # frame.rsv1 is True at this point
                self.decode_cont_data = True

        # Uncompress compressed frames.
        data = frame.data
        if frame.fin:
            data += _EMPTY_UNCOMPRESSED_BLOCK
        data = self.decoder.decompress(data)

        return frame._replace(data=data, rsv1=False)

    def encode(self, frame):
        """
        Encode an outgoing frame.

        """
        # Skip control frames.
        if frame.opcode in CTRL_OPCODES:
            return frame

        # Compress data frames.
        # Since we don't do fragmentation, this is easy.
        data = (
            self.encoder.compress(frame.data) +
            self.encoder.flush(zlib.Z_SYNC_FLUSH)
        )
        if data.endswith(_EMPTY_UNCOMPRESSED_BLOCK):
            data = data[:-4]

        return frame._replace(data=data, rsv1=frame.opcode != OP_CONT)
