#!/usr/bin/env python

import asyncio
import json

import aioredis
import django
import websockets

django.setup()

from django.contrib.contenttypes.models import ContentType

# Reuse our custom protocol to authenticate connections
from authentication import ServerProtocol


CONNECTIONS = {}


def get_content_types(user):
    """Return the set of IDs of content types visible by user."""
    # This does only three database queries because Django caches
    # all permissions on the first call to user.has_perm(...).
    return {
        ct.id
        for ct in ContentType.objects.all()
        if user.has_perm(f"{ct.app_label}.view_{ct.model}")
        or user.has_perm(f"{ct.app_label}.change_{ct.model}")
    }


async def handler(websocket, path):
    """Register connection in CONNECTIONS dict, until it's closed."""
    ct_ids = await asyncio.to_thread(get_content_types, websocket.user)
    CONNECTIONS[websocket] = {"content_type_ids": ct_ids}
    try:
        await websocket.wait_closed()
    finally:
        del CONNECTIONS[websocket]


async def process_events():
    """Listen to events in Redis and process them."""
    redis = aioredis.from_url("redis://127.0.0.1:6379/1")
    pubsub = redis.pubsub()
    await pubsub.subscribe("events")
    async for message in pubsub.listen():
        if message["type"] != "message":
            continue
        payload = message["data"].decode()
        # Broadcast event to all users who have permissions to see it.
        event = json.loads(payload)
        for websocket, connection in CONNECTIONS.items():
            if event["content_type_id"] in connection["content_type_ids"]:
                asyncio.create_task(websocket.send(payload))


async def main():
    async with websockets.serve(
        handler,
        "localhost",
        8888,
        create_protocol=ServerProtocol,
    ):
        await process_events()  # runs forever


if __name__ == "__main__":
    asyncio.run(main())
