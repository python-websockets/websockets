import trio.testing

from websockets.trio.utils import *

from .utils import IsolatedTrioTestCase


class UtilsTests(IsolatedTrioTestCase):
    async def test_race_events(self):
        event1 = trio.Event()
        event2 = trio.Event()
        done = trio.Event()

        async def waiter():
            await race_events(event1, event2)
            done.set()

        async with trio.open_nursery() as nursery:
            nursery.start_soon(waiter)
            await trio.testing.wait_all_tasks_blocked()
            self.assertFalse(done.is_set())

            event1.set()
            await trio.testing.wait_all_tasks_blocked()
            self.assertTrue(done.is_set())

    async def test_race_events_cancelled(self):
        event1 = trio.Event()
        event2 = trio.Event()

        async def waiter():
            with trio.move_on_after(0):
                await race_events(event1, event2)

        async with trio.open_nursery() as nursery:
            nursery.start_soon(waiter)

    async def test_race_events_no_events(self):
        with self.assertRaises(ValueError):
            await race_events()
