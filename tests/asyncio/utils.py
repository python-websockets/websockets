async def alist(async_iterable):
    items = []
    async for item in async_iterable:
        items.append(item)
    return items
