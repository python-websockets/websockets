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

        This can result in out-of-order writes, which is unrealistic.

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

        This can result in out-of-order writes, which is unrealistic.

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

    Since ``write()`` and ``write_eof()`` are not coroutines, this effect is
    achieved by scheduling writes at a later time, after the methods return.
    This can easily result in out-of-order writes, which is unrealistic.

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
        if not self.drop_write:
            if self.delay_write is not None:
                self.loop.call_later(self.delay_write, self.transport.write, data)
            else:
                self.transport.write(data)

    def write_eof(self):
        if not self.drop_write_eof:
            if self.delay_write_eof is not None:
                self.loop.call_later(self.delay_write_eof, self.transport.write_eof)
            else:
                self.transport.write_eof()
