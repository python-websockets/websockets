#!/usr/bin/env python

import asyncio
import statistics
import tracemalloc

from websockets.asyncio.client import connect
from websockets.extensions.permessage_deflate import ClientPerMessageDeflateFactory


CLIENTS = 20
INTERVAL = 1 / 10  # seconds

WB, ML = 12, 5

MEM_SIZE = []


async def client(num):
    # Space out connections to make them sequential.
    await asyncio.sleep(num * INTERVAL)

    tracemalloc.start()

    async with connect(
        "ws://localhost:8765",
        extensions=[
            ClientPerMessageDeflateFactory(
                server_max_window_bits=WB,
                client_max_window_bits=WB,
                compress_settings={"memLevel": ML},
            )
        ],
    ) as ws:
        await ws.send("hello")
        await ws.recv()

        await ws.send(b"hello")
        await ws.recv()

        MEM_SIZE.append(tracemalloc.get_traced_memory()[0])
        tracemalloc.stop()

        # Hold connection open until the end of the test.
        await asyncio.sleep((CLIENTS + 1 - num) * INTERVAL)


async def clients():
    # Start one more client than necessary because we will ignore
    # non-representative results from the first connection.
    await asyncio.gather(*[client(num) for num in range(CLIENTS + 1)])


asyncio.run(clients())


# First connection incurs non-representative setup costs.
del MEM_SIZE[0]

print(f"µ = {statistics.mean(MEM_SIZE) / 1024:.1f} KiB")
print(f"σ = {statistics.stdev(MEM_SIZE) / 1024:.1f} KiB")
