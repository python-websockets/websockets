class Connect:
    """
    This class wraps :func:`connect` on Python 3.5 and above.

    It can be used as an asynchronous context manager.

    """

    __wrapped__ = NotImplemented

    def __init__(self, *args, **kwargs):
        connect = self.__class__.__wrapped__
        self.connect_coroutine = connect(*args, **kwargs)

    def __await__(self):
        return (yield from self.connect_coroutine)

    async def __aenter__(self):
        self.websocket = await self
        return self.websocket

    async def __aexit__(self, exc_type, exc_value, traceback):
        await self.websocket.close()

    __iter__ = __await__
