import contextlib

import trio

from websockets.trio.connection import Connection


class InterceptingConnection(Connection):
    """
    Connection subclass that can intercept outgoing packets.

    By interfacing with this connection, we simulate network conditions
    affecting what the component being tested receives during a test.

    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stream = InterceptingStream(self.stream)

    @contextlib.contextmanager
    def delay_frames_sent(self, delay):
        """
        Add a delay before sending frames.

        Delays cumulate: they're added before every frame or before EOF.

        """
        assert self.stream.delay_send_all is None
        self.stream.delay_send_all = delay
        try:
            yield
        finally:
            self.stream.delay_send_all = None

    @contextlib.contextmanager
    def delay_eof_sent(self, delay):
        """
        Add a delay before sending EOF.

        Delays cumulate: they're added before every frame or before EOF.

        """
        assert self.stream.delay_send_eof is None
        self.stream.delay_send_eof = delay
        try:
            yield
        finally:
            self.stream.delay_send_eof = None

    @contextlib.contextmanager
    def drop_frames_sent(self):
        """
        Prevent frames from being sent.

        Since TCP is reliable, sending frames or EOF afterwards is unrealistic.

        """
        assert not self.stream.drop_send_all
        self.stream.drop_send_all = True
        try:
            yield
        finally:
            self.stream.drop_send_all = False

    @contextlib.contextmanager
    def drop_eof_sent(self):
        """
        Prevent EOF from being sent.

        Since TCP is reliable, sending frames or EOF afterwards is unrealistic.

        """
        assert not self.stream.drop_send_eof
        self.stream.drop_send_eof = True
        try:
            yield
        finally:
            self.stream.drop_send_eof = False


class InterceptingStream:
    """
    Stream wrapper that intercepts calls to ``send_all()`` and ``send_eof()``.

    This is coupled to the implementation, which relies on these two methods.

    """

    # We cannot delay EOF with trio's virtual streams because close_hook is
    # synchronous. We adopt the same approach as the other implementations.

    def __init__(self, stream):
        self.stream = stream
        self.delay_send_all = None
        self.delay_send_eof = None
        self.drop_send_all = False
        self.drop_send_eof = False

    def __getattr__(self, name):
        return getattr(self.stream, name)

    async def send_all(self, data):
        if self.delay_send_all is not None:
            await trio.sleep(self.delay_send_all)
        if not self.drop_send_all:
            await self.stream.send_all(data)

    async def send_eof(self):
        if self.delay_send_eof is not None:
            await trio.sleep(self.delay_send_eof)
        if not self.drop_send_eof:
            await self.stream.send_eof()


trio.abc.HalfCloseableStream.register(InterceptingStream)
