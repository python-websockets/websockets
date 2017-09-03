from ..exceptions import ConnectionClosed


async def __aiter__(self):
    try:
        while True:
            yield await self.recv()
    except ConnectionClosed as exc:
        if exc.code == 1000:
            return
        else:
            raise
