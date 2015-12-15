import asyncio
import websockets.client


class Connect:

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    async def __aenter__(self):
        self._websocket = await self
        return self._websocket

    def __iter__(self):
        coro = websockets.client._connect(*self.args, **self.kwargs)
        return (yield from coro)

    __await__ = __iter__

    async def __aexit__(self, exc_type, exc_value, traceback):
        close_result = await self._websocket.close()
        del self._websocket
        return close_result
