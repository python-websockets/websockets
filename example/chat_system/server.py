import websockets
import datetime
import asyncio
import random


MESSAGES = ['lol', 'sigh', 'ugh', '...']

async def random_messages(ws):
    while True:
        wait_time_in_seconds = random.uniform(2, 5)
        await asyncio.sleep(wait_time_in_seconds)
        await ws.send(random.choice(MESSAGES))


async def server(ws, path):
    rand_task = asyncio.create_task(random_messages(ws))
    async for msg in ws:
        print(msg)
        await ws.send(f'{datetime.datetime.utcnow()}: {msg}')


asyncio.get_event_loop().run_until_complete(websockets.serve(server, '127.0.0.1', 50001))
asyncio.get_event_loop().run_forever()
