import asyncio
import logging

from websockets.asyncio.server import serve


logging.basicConfig(level=logging.WARNING)

HOST, PORT = "0.0.0.0", 9002


async def echo(ws):
    async for msg in ws:
        await ws.send(msg)


async def main():
    async with serve(
        echo,
        HOST,
        PORT,
        server_header="websockets.sync",
        max_size=2**25,
    ) as server:
        try:
            await server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    asyncio.run(main())