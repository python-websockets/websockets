#!/usr/bin/env python

import asyncio
import signal
import statistics
import tracemalloc

import websockets
from websockets.extensions import permessage_deflate


CLIENTS = 10
INTERVAL = 1 / 10  # seconds

MEM_SIZE = []


async def handler(ws, path):
    msg = await ws.recv()
    await ws.send(msg)

    msg = await ws.recv()
    await ws.send(msg)

    MEM_SIZE.append(tracemalloc.get_traced_memory()[0])
    tracemalloc.stop()

    tracemalloc.start()

    # Hold connection open until the end of the test.
    await asyncio.sleep(CLIENTS * INTERVAL)


async def mem_server():
    loop = asyncio.get_running_loop()
    stop = loop.create_future()
    # Set the stop condition when receiving SIGTERM.
    loop.add_signal_handler(signal.SIGTERM, stop.set_result, None)
    async with websockets.serve(
        handler,
        "localhost",
        8765,
        extensions=[
            permessage_deflate.ServerPerMessageDeflateFactory(
                server_max_window_bits=10,
                client_max_window_bits=10,
                compress_settings={"memLevel": 3},
            )
        ],
    ):
        tracemalloc.start()
        await stop


asyncio.run(mem_server())


# First connection may incur non-representative setup costs.
del MEM_SIZE[0]

print(f"µ = {statistics.mean(MEM_SIZE) / 1024:.1f} KiB")
print(f"σ = {statistics.stdev(MEM_SIZE) / 1024:.1f} KiB")
