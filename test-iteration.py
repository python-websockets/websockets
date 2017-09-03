import asyncio
import logging
import websockets


async def demo():
    async with websockets.connect('ws://echo.websocket.org') as websocket:
        for i in range(3):
            await websocket.send('hello!')
        async for msg in websocket:
            print('received:', msg)


async def run():
    await asyncio.wait_for(demo(), timeout=3)


logging.basicConfig(level=logging.DEBUG)
loop = asyncio.get_event_loop()

loop.set_debug(True)
loop.run_until_complete(run())
loop.close()
