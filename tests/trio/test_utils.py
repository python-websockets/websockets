import trio.testing

from websockets.trio.utils import *

from .utils import IsolatedTrioTestCase


class UtilsTests(IsolatedTrioTestCase):
    async def test_wait_for_any_event(self):
        event1 = trio.Event()
        event2 = trio.Event()
        done = trio.Event()

        async def waiter():
            await wait_for_any_event(event1, event2)
            done.set()

        self.nursery.start_soon(waiter)
        await trio.testing.wait_all_tasks_blocked()
        self.assertFalse(done.is_set())

        event1.set()
        await trio.testing.wait_all_tasks_blocked()
        self.assertTrue(done.is_set())

    async def test_wait_for_any_event_no_events(self):
        with self.assertRaises(ValueError):
            await wait_for_any_event()
