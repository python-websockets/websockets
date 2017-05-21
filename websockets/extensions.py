import zlib

from .framing import CTRL_OPCODES, OP_CONT

__all__ = ['PerMessageDeflate', 'parse_extensions']

_EMPTY_UNCOMPRESSED_BLOCK = b'\x00\x00\xff\xff'


def unquote_value(value):
    if value and value[0] == value[-1] == '"':
        return value[1:-1]
    return value


def parse_extensions(header):
    """
    Parse an extension header and return a list of extension/parameters
    :param header: str
    :return: [('extension name', {parameters dict}), ...]
    """
    extensions = []
    header = header.replace('\n', ',')
    for ext_string in header.split(','):
        ext_name, *params_list = ext_string.strip().split(';')
        ext_name = ext_name.strip()
        if not ext_name:
            # Can happen with an initial carriage return
            continue
        parameters = {}
        for param in params_list:
            if '=' in param:
                param, param_value = param.split('=', 1)
                param_value = unquote_value(param_value.strip())
            else:
                param_value = None
            parameters[param.strip()] = param_value
        extensions.append((ext_name, parameters))
    return extensions


class PerMessageDeflate:
    """
    Compression Extensions for WebSocket (`RFC 7692`_).

    .. _RFC 7692: http://tools.ietf.org/html/rfc7692

    """

    def __init__(self, is_client, parameters, *,
                 server_no_context_takeover=False,
                 client_no_context_takeover=False,
                 server_max_window_bits=15,
                 client_max_window_bits=15):
        self.is_client = is_client
        self.server_no_context_takeover = server_no_context_takeover
        self.client_no_context_takeover = client_no_context_takeover
        self.server_max_window_bits = server_max_window_bits
        self.client_max_window_bits = client_max_window_bits

        for param, value in parameters.items():
            if param == 'server_no_context_takeover':
                assert value is None
                self.server_no_context_takeover = True
            elif param == 'client_no_context_takeover':
                assert value is None
                self.client_no_context_takeover = True
            elif param.startswith('client_max_window_bits'):
                if value:
                    window_bits = int(value)
                    assert 8 <= window_bits <= 15
                    window_bits = min(window_bits, self.client_max_window_bits)
                    self.client_max_window_bits = window_bits
            elif param.startswith('server_max_window_bits'):
                assert value is not None
                window_bits = int(value)
                assert 8 <= window_bits <= 15
                window_bits = min(window_bits, self.server_max_window_bits)
                self.server_max_window_bits = window_bits
            else:
                raise ValueError('invalid parameter')

        # Internal state.
        if self.is_client:
            self.transient_encoder = self.client_no_context_takeover
            self.transient_decoder = self.server_no_context_takeover
        else:
            self.transient_encoder = self.server_no_context_takeover
            self.transient_decoder = self.client_no_context_takeover

        if self.transient_decoder:
            self.decoder = None
        else:
            self.decoder = zlib.decompressobj(
                wbits=-(
                    self.server_max_window_bits
                    if self.is_client else
                    self.client_max_window_bits
                ),
            )

        if self.transient_encoder:
            self.encoder = None
        else:
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
            if not frame.fin:  # frame.rsv1 is True at this point
                self.decode_cont_data = True

            if self.transient_decoder:
                self.decoder = zlib.decompressobj(
                    wbits=-(
                        self.server_max_window_bits
                        if self.is_client else
                        self.client_max_window_bits
                    ),
                )

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

        if self.transient_encoder:
            self.encoder = zlib.compressobj(
                wbits=-(
                    self.client_max_window_bits
                    if self.is_client else
                    self.server_max_window_bits
                ),
            )

        # Compress data frames.
        # Since we don't do fragmentation, this is easy.
        data = (
            self.encoder.compress(frame.data) +
            self.encoder.flush(zlib.Z_SYNC_FLUSH)
        )
        if data.endswith(_EMPTY_UNCOMPRESSED_BLOCK):
            data = data[:-4]

        return frame._replace(data=data, rsv1=frame.opcode != OP_CONT)

    def response(self):
        response = self.name()
        if self.server_no_context_takeover:
            response += '; server_no_context_takeover'
        if self.client_no_context_takeover:
            response += '; client_no_context_takeover'
        if self.client_max_window_bits < 15:
            response += '; client_max_window_bits={}'.format(
                self.client_max_window_bits)
        if self.server_max_window_bits < 15:
            response += '; server_max_window_bits={}'.format(
                self.server_max_window_bits)
        return response
