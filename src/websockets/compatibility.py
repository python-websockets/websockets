import asyncio

try:  # pragma: no cover
    asyncio_create_task = asyncio.create_task  # Python ≥ 3.7
except AttributeError:  # pragma: no cover
    asyncio_create_task = asyncio.ensure_future  # Python < 3.7
