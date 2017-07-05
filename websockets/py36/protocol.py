async def __aiter__(self):
    while True:
        yield await self.recv()
