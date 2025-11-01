import asyncio
import contextlib

from websockets.asyncio.connection import Connection


class InterceptingConnection(Connection):
    """
    Connection subclass that can intercept outgoing packets.

    By interfacing with this connection, we simulate network conditions
    affecting what the component being tested receives during a test.

    """

    def connection_made(self, transport):
        super().connection_made(InterceptingTransport(transport))

    @contextlib.contextmanager
    def delay_frames_sent(self, delay):
        """
        Add a delay before sending frames.

        Misuse can result in out-of-order writes, which is unrealistic.

        """
        assert self.transport.delay_write is None
        self.transport.delay_write = delay
        try:
            yield
        finally:
            self.transport.delay_write = None

    @contextlib.contextmanager
    def delay_eof_sent(self, delay):
        """
        Add a delay before sending EOF.

        Misuse can result in out-of-order writes, which is unrealistic.

        """
        assert self.transport.delay_write_eof is None
        self.transport.delay_write_eof = delay
        try:
            yield
        finally:
            self.transport.delay_write_eof = None

    @contextlib.contextmanager
    def drop_frames_sent(self):
        """
        Prevent frames from being sent.

        Since TCP is reliable, sending frames or EOF afterwards is unrealistic.

        """
        assert not self.transport.drop_write
        self.transport.drop_write = True
        try:
            yield
        finally:
            self.transport.drop_write = False

    @contextlib.contextmanager
    def drop_eof_sent(self):
        """
        Prevent EOF from being sent.

        Since TCP is reliable, sending frames or EOF afterwards is unrealistic.

        """
        assert not self.transport.drop_write_eof
        self.transport.drop_write_eof = True
        try:
            yield
        finally:
            self.transport.drop_write_eof = False


class InterceptingTransport:
    """
    Transport wrapper that intercepts calls to ``write()`` and ``write_eof()``.

    This is coupled to the implementation, which relies on these two methods.

    Since ``write()`` and ``write_eof()`` are synchronous, we can only schedule
    writes at a later time, after they return. This is unrealistic and can lead
    to out-of-order writes if tests aren't written carefully.

    """

    def __init__(self, transport):
        self.loop = asyncio.get_running_loop()
        self.transport = transport
        self.delay_write = None
        self.delay_write_eof = None
        self.drop_write = False
        self.drop_write_eof = False

    def __getattr__(self, name):
        return getattr(self.transport, name)

    def write(self, data):
        if self.delay_write is not None:
            assert not self.drop_write
            self.loop.call_later(self.delay_write, self.transport.write, data)
        elif not self.drop_write:
            self.transport.write(data)

    def write_eof(self):
        if self.delay_write_eof is not None:
            assert not self.drop_write_eof
            self.loop.call_later(self.delay_write_eof, self.transport.write_eof)
        elif not self.drop_write_eof:
            self.transport.write_eof()
