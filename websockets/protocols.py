"""Tulip protocols."""

__all__ = ['WebSocketFramingProtocol']

import tulip

from .framing import *
from .handshake import *


class WebSocketFramingProtocol(WebSocketFraming, tulip.Protocol):
    """
    WebSocket frames implementation as a Tulip protocol.
    """

    def __init__(self, *args, **kwargs):
        # The reader and writer will be set by connection_made.
        super().__init__(None, None, *args, **kwargs)

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
        yield from super().close(data)
        self.transport.close()
