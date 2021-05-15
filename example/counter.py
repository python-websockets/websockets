#!/usr/bin/env python

# WS server example that synchronizes state across clients

import asyncio
import json
import logging
import websockets

logging.basicConfig()

STATE = {"value": 0}

USERS = set()


def state_event():
    return json.dumps({"type": "state", **STATE})


def users_event():
    return json.dumps({"type": "users", "count": len(USERS)})


async def broadcast(message):
    # asyncio.wait doesn't accept an empty list
    if not USERS:
        return
    # Ignore return value. If a user disconnects before we send
    # the message to them, there's nothing we can do anyway.
    await asyncio.wait([
        asyncio.create_task(user.send(message))
        for user in USERS
    ])


async def counter(websocket, path):
    try:
        # Register user
        USERS.add(websocket)
        await broadcast(users_event())
        # Send current state to user
        await websocket.send(state_event())
        # Manage state changes
        async for message in websocket:
            data = json.loads(message)
            if data["action"] == "minus":
                STATE["value"] -= 1
                await broadcast(state_event())
            elif data["action"] == "plus":
                STATE["value"] += 1
                await broadcast(state_event())
            else:
                logging.error("unsupported event: %s", data)
    finally:
        # Unregister user
        USERS.remove(websocket)
        await broadcast(users_event())


async def main():
    async with websockets.serve(counter, "localhost", 6789):
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())
