async def __aenter__(self):
    return await self


async def __aexit__(self, exc_type, exc_value, traceback):
    self.ws_server.close()
    await self.ws_server.wait_closed()


async def __await_impl__(self):
    # Duplicated with __iter__ because Python 3.7 requires an async function
    # (as explained in __await__ below) which Python 3.4 doesn't support.
    server = await self._creating_server
    self.ws_server.wrap(server)
    return self.ws_server


def __await__(self):
    # __await__() must return a type that I don't know how to obtain except
    # by calling __await__() on the return value of an async function.
    # I'm not finding a better way to take advantage of PEP 492.
    return __await_impl__(self).__await__()
