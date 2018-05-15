from ..exceptions import ConnectionClosed


async def __aiter__(self):
    """
    Iterate on received messages.

    Exit normally when the connection is closed with code 1000.

    Raise an exception in other cases.

    """
    try:
        while True:
            yield await self.recv()
    except ConnectionClosed as exc:
        if exc.code == 1000 or exc.code == 1001:
            return
        else:
            raise
