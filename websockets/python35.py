

class WebSocketProtocolContextManagerMixin():

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()
