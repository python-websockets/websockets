import asyncio
import datetime
import random
import string
import websockets


# websocket to nickname
USERS = {}

MESSAGES = ['sigh', 'ugh', '...']


def register(websocket):
    while True:
        nickname = ''.join(random.choice(string.ascii_lowercase) for _ in range(8))
        if nickname not in USERS.values():
            break
    USERS[websocket] = nickname


async def send_all_users(nickname, message):
    for websocket in USERS.keys():
        await websocket.send(f'[{datetime.datetime.utcnow()}] <{nickname}>: {message}')


async def bot_messages(websocket):
    while True:
        wait_time_in_seconds = random.uniform(2, 5)
        await asyncio.sleep(wait_time_in_seconds)
        random_message = random.choice(MESSAGES)
        await send_all_users('Marvin', random_message)


async def server(websocket, path):
    register(websocket)
    try:
        await websocket.send(f'Your nickname is "{USERS[websocket]}".')
        rand_task = asyncio.create_task(bot_messages(websocket))
        async for message in websocket:
            for other_websocket in USERS:
                await other_websocket.send(f'[{datetime.datetime.utcnow()}] <{USERS[websocket]}>: {message}')
    finally:
        unregister(websocket)


asyncio.get_event_loop().run_until_complete(websockets.serve(server, '127.0.0.1', 50001))
asyncio.get_event_loop().run_forever()
