import trio


__all__ = ["wait_for_any_event"]


# Based on https://trio.readthedocs.io/en/stable/reference-core.html#custom-supervisors


async def jockey(event: trio.Event, cancel_scope: trio.CancelScope) -> None:
    await event.wait()
    cancel_scope.cancel()


async def wait_for_any_event(*events: trio.Event) -> None:
    """
    Wait for any of the given events to be set.

    Args:
        *events: The events to wait for.

    """
    if not events:
        raise ValueError("no events provided")

    async with trio.open_nursery() as nursery:
        for event in events:
            nursery.start_soon(jockey, event, nursery.cancel_scope)
