import asyncio
import logging

from websockets.asyncio.server import serve


logging.basicConfig(level=logging.WARNING)

# Uncomment this line to make only websockets more verbose.
# logging.getLogger('websockets').setLevel(logging.DEBUG)


HOST, PORT = "127.0.0.1", 8642


async def echo(ws):
    async for msg in ws:
        await ws.send(msg)


async def main():
    with serve(echo, HOST, PORT, max_size=2 ** 25, max_queue=1):
        try:
            await asyncio.get_running_loop().create_future()  # run forever
        except KeyboardInterrupt:
            pass


asyncio.run(main())
