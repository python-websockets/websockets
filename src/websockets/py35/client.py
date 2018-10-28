async def __aenter__(self):
    return await self


async def __aexit__(self, exc_type, exc_value, traceback):
    await self.ws_client.close()


async def __await_impl__(self):
    # Duplicated with __iter__ because Python 3.7 requires an async function
    # (as explained in __await__ below) which Python 3.4 doesn't support.
    transport, protocol = await self._creating_connection

    try:
        await protocol.handshake(
            self._wsuri,
            origin=self._origin,
            available_extensions=protocol.available_extensions,
            available_subprotocols=protocol.available_subprotocols,
            extra_headers=protocol.extra_headers,
        )
    except Exception:
        protocol.fail_connection()
        await protocol.wait_closed()
        raise

    self.ws_client = protocol
    return protocol


def __await__(self):
    # __await__() must return a type that I don't know how to obtain except
    # by calling __await__() on the return value of an async function.
    # I'm not finding a better way to take advantage of PEP 492.
    return __await_impl__(self).__await__()
