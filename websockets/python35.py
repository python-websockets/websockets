
class _Connect:

    _client_connect_coro = NotImplemented

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    def __iter__(self):
        cls = self.__class__
        coro = cls._client_connect_coro(*self.args, **self.kwargs)
        return (yield from coro)

    __await__ = __iter__

    async def __aenter__(self):
        self._websocket = await self
        return self._websocket

    async def __aexit__(self, exc_type, exc_value, traceback):
        await self._websocket.close()
        del self._websocket


def connect_coro_wrapper(client_connect_coro):
    _Connect._client_connect_coro = client_connect_coro
    return _Connect
