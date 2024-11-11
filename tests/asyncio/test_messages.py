import asyncio
import unittest
import unittest.mock

from websockets.asyncio.compatibility import aiter, anext
from websockets.asyncio.messages import *
from websockets.asyncio.messages import SimpleQueue
from websockets.exceptions import ConcurrencyError
from websockets.frames import OP_BINARY, OP_CONT, OP_TEXT, Frame

from .utils import alist


class SimpleQueueTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.queue = SimpleQueue()

    async def test_len(self):
        """__len__ returns queue length."""
        self.assertEqual(len(self.queue), 0)
        self.queue.put(42)
        self.assertEqual(len(self.queue), 1)
        await self.queue.get()
        self.assertEqual(len(self.queue), 0)

    async def test_put_then_get(self):
        """get returns an item that is already put."""
        self.queue.put(42)
        item = await self.queue.get()
        self.assertEqual(item, 42)

    async def test_get_then_put(self):
        """get returns an item when it is put."""
        getter_task = asyncio.create_task(self.queue.get())
        await asyncio.sleep(0)  # let the task start
        self.queue.put(42)
        item = await getter_task
        self.assertEqual(item, 42)

    async def test_reset(self):
        """reset sets the content of the queue."""
        self.queue.reset([42])
        item = await self.queue.get()
        self.assertEqual(item, 42)

    async def test_abort(self):
        """abort throws an exception in get."""
        getter_task = asyncio.create_task(self.queue.get())
        await asyncio.sleep(0)  # let the task start
        self.queue.abort()
        with self.assertRaises(EOFError):
            await getter_task


class AssemblerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.pause = unittest.mock.Mock()
        self.resume = unittest.mock.Mock()
        self.assembler = Assembler(high=2, low=1, pause=self.pause, resume=self.resume)

    # Test get

    async def test_get_text_message_already_received(self):
        """get returns a text message that is already received."""
        self.assembler.put(Frame(OP_TEXT, b"caf\xc3\xa9"))
        message = await self.assembler.get()
        self.assertEqual(message, "café")

    async def test_get_binary_message_already_received(self):
        """get returns a binary message that is already received."""
        self.assembler.put(Frame(OP_BINARY, b"tea"))
        message = await self.assembler.get()
        self.assertEqual(message, b"tea")

    async def test_get_text_message_not_received_yet(self):
        """get returns a text message when it is received."""
        getter_task = asyncio.create_task(self.assembler.get())
        await asyncio.sleep(0)  # let the event loop start getter_task
        self.assembler.put(Frame(OP_TEXT, b"caf\xc3\xa9"))
        message = await getter_task
        self.assertEqual(message, "café")

    async def test_get_binary_message_not_received_yet(self):
        """get returns a binary message when it is received."""
        getter_task = asyncio.create_task(self.assembler.get())
        await asyncio.sleep(0)  # let the event loop start getter_task
        self.assembler.put(Frame(OP_BINARY, b"tea"))
        message = await getter_task
        self.assertEqual(message, b"tea")

    async def test_get_fragmented_text_message_already_received(self):
        """get reassembles a fragmented a text message that is already received."""
        self.assembler.put(Frame(OP_TEXT, b"ca", fin=False))
        self.assembler.put(Frame(OP_CONT, b"f\xc3", fin=False))
        self.assembler.put(Frame(OP_CONT, b"\xa9"))
        message = await self.assembler.get()
        self.assertEqual(message, "café")

    async def test_get_fragmented_binary_message_already_received(self):
        """get reassembles a fragmented binary message that is already received."""
        self.assembler.put(Frame(OP_BINARY, b"t", fin=False))
        self.assembler.put(Frame(OP_CONT, b"e", fin=False))
        self.assembler.put(Frame(OP_CONT, b"a"))
        message = await self.assembler.get()
        self.assertEqual(message, b"tea")

    async def test_get_fragmented_text_message_not_received_yet(self):
        """get reassembles a fragmented text message when it is received."""
        getter_task = asyncio.create_task(self.assembler.get())
        self.assembler.put(Frame(OP_TEXT, b"ca", fin=False))
        self.assembler.put(Frame(OP_CONT, b"f\xc3", fin=False))
        self.assembler.put(Frame(OP_CONT, b"\xa9"))
        message = await getter_task
        self.assertEqual(message, "café")

    async def test_get_fragmented_binary_message_not_received_yet(self):
        """get reassembles a fragmented binary message when it is received."""
        getter_task = asyncio.create_task(self.assembler.get())
        self.assembler.put(Frame(OP_BINARY, b"t", fin=False))
        self.assembler.put(Frame(OP_CONT, b"e", fin=False))
        self.assembler.put(Frame(OP_CONT, b"a"))
        message = await getter_task
        self.assertEqual(message, b"tea")

    async def test_get_fragmented_text_message_being_received(self):
        """get reassembles a fragmented text message that is partially received."""
        self.assembler.put(Frame(OP_TEXT, b"ca", fin=False))
        getter_task = asyncio.create_task(self.assembler.get())
        self.assembler.put(Frame(OP_CONT, b"f\xc3", fin=False))
        self.assembler.put(Frame(OP_CONT, b"\xa9"))
        message = await getter_task
        self.assertEqual(message, "café")

    async def test_get_fragmented_binary_message_being_received(self):
        """get reassembles a fragmented binary message that is partially received."""
        self.assembler.put(Frame(OP_BINARY, b"t", fin=False))
        getter_task = asyncio.create_task(self.assembler.get())
        self.assembler.put(Frame(OP_CONT, b"e", fin=False))
        self.assembler.put(Frame(OP_CONT, b"a"))
        message = await getter_task
        self.assertEqual(message, b"tea")

    async def test_get_encoded_text_message(self):
        """get returns a text message without UTF-8 decoding."""
        self.assembler.put(Frame(OP_TEXT, b"caf\xc3\xa9"))
        message = await self.assembler.get(decode=False)
        self.assertEqual(message, b"caf\xc3\xa9")

    async def test_get_decoded_binary_message(self):
        """get returns a binary message with UTF-8 decoding."""
        self.assembler.put(Frame(OP_BINARY, b"tea"))
        message = await self.assembler.get(decode=True)
        self.assertEqual(message, "tea")

    async def test_get_resumes_reading(self):
        """get resumes reading when queue goes below the low-water mark."""
        self.assembler.put(Frame(OP_TEXT, b"caf\xc3\xa9"))
        self.assembler.put(Frame(OP_TEXT, b"more caf\xc3\xa9"))
        self.assembler.put(Frame(OP_TEXT, b"water"))

        # queue is above the low-water mark
        await self.assembler.get()
        self.resume.assert_not_called()

        # queue is at the low-water mark
        await self.assembler.get()
        self.resume.assert_called_once_with()

        # queue is below the low-water mark
        await self.assembler.get()
        self.resume.assert_called_once_with()

    async def test_get_does_not_resume_reading(self):
        """get does not resume reading when the low-water mark is unset."""
        self.assembler.low = None

        self.assembler.put(Frame(OP_TEXT, b"caf\xc3\xa9"))
        self.assembler.put(Frame(OP_TEXT, b"more caf\xc3\xa9"))
        self.assembler.put(Frame(OP_TEXT, b"water"))
        await self.assembler.get()
        await self.assembler.get()
        await self.assembler.get()

        self.resume.assert_not_called()

    async def test_cancel_get_before_first_frame(self):
        """get can be canceled safely before reading the first frame."""
        getter_task = asyncio.create_task(self.assembler.get())
        await asyncio.sleep(0)  # let the event loop start getter_task
        getter_task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await getter_task

        self.assembler.put(Frame(OP_TEXT, b"caf\xc3\xa9"))

        message = await self.assembler.get()
        self.assertEqual(message, "café")

    async def test_cancel_get_after_first_frame(self):
        """get can be canceled safely after reading the first frame."""
        self.assembler.put(Frame(OP_TEXT, b"ca", fin=False))

        getter_task = asyncio.create_task(self.assembler.get())
        await asyncio.sleep(0)  # let the event loop start getter_task
        getter_task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await getter_task

        self.assembler.put(Frame(OP_CONT, b"f\xc3", fin=False))
        self.assembler.put(Frame(OP_CONT, b"\xa9"))

        message = await self.assembler.get()
        self.assertEqual(message, "café")

    # Test get_iter

    async def test_get_iter_text_message_already_received(self):
        """get_iter yields a text message that is already received."""
        self.assembler.put(Frame(OP_TEXT, b"caf\xc3\xa9"))
        fragments = await alist(self.assembler.get_iter())
        self.assertEqual(fragments, ["café"])

    async def test_get_iter_binary_message_already_received(self):
        """get_iter yields a binary message that is already received."""
        self.assembler.put(Frame(OP_BINARY, b"tea"))
        fragments = await alist(self.assembler.get_iter())
        self.assertEqual(fragments, [b"tea"])

    async def test_get_iter_text_message_not_received_yet(self):
        """get_iter yields a text message when it is received."""
        getter_task = asyncio.create_task(alist(self.assembler.get_iter()))
        await asyncio.sleep(0)  # let the event loop start getter_task
        self.assembler.put(Frame(OP_TEXT, b"caf\xc3\xa9"))
        fragments = await getter_task
        self.assertEqual(fragments, ["café"])

    async def test_get_iter_binary_message_not_received_yet(self):
        """get_iter yields a binary message when it is received."""
        getter_task = asyncio.create_task(alist(self.assembler.get_iter()))
        await asyncio.sleep(0)  # let the event loop start getter_task
        self.assembler.put(Frame(OP_BINARY, b"tea"))
        fragments = await getter_task
        self.assertEqual(fragments, [b"tea"])

    async def test_get_iter_fragmented_text_message_already_received(self):
        """get_iter yields a fragmented text message that is already received."""
        self.assembler.put(Frame(OP_TEXT, b"ca", fin=False))
        self.assembler.put(Frame(OP_CONT, b"f\xc3", fin=False))
        self.assembler.put(Frame(OP_CONT, b"\xa9"))
        fragments = await alist(self.assembler.get_iter())
        self.assertEqual(fragments, ["ca", "f", "é"])

    async def test_get_iter_fragmented_binary_message_already_received(self):
        """get_iter yields a fragmented binary message that is already received."""
        self.assembler.put(Frame(OP_BINARY, b"t", fin=False))
        self.assembler.put(Frame(OP_CONT, b"e", fin=False))
        self.assembler.put(Frame(OP_CONT, b"a"))
        fragments = await alist(self.assembler.get_iter())
        self.assertEqual(fragments, [b"t", b"e", b"a"])

    async def test_get_iter_fragmented_text_message_not_received_yet(self):
        """get_iter yields a fragmented text message when it is received."""
        iterator = aiter(self.assembler.get_iter())
        self.assembler.put(Frame(OP_TEXT, b"ca", fin=False))
        self.assertEqual(await anext(iterator), "ca")
        self.assembler.put(Frame(OP_CONT, b"f\xc3", fin=False))
        self.assertEqual(await anext(iterator), "f")
        self.assembler.put(Frame(OP_CONT, b"\xa9"))
        self.assertEqual(await anext(iterator), "é")

    async def test_get_iter_fragmented_binary_message_not_received_yet(self):
        """get_iter yields a fragmented binary message when it is received."""
        iterator = aiter(self.assembler.get_iter())
        self.assembler.put(Frame(OP_BINARY, b"t", fin=False))
        self.assertEqual(await anext(iterator), b"t")
        self.assembler.put(Frame(OP_CONT, b"e", fin=False))
        self.assertEqual(await anext(iterator), b"e")
        self.assembler.put(Frame(OP_CONT, b"a"))
        self.assertEqual(await anext(iterator), b"a")

    async def test_get_iter_fragmented_text_message_being_received(self):
        """get_iter yields a fragmented text message that is partially received."""
        self.assembler.put(Frame(OP_TEXT, b"ca", fin=False))
        iterator = aiter(self.assembler.get_iter())
        self.assertEqual(await anext(iterator), "ca")
        self.assembler.put(Frame(OP_CONT, b"f\xc3", fin=False))
        self.assertEqual(await anext(iterator), "f")
        self.assembler.put(Frame(OP_CONT, b"\xa9"))
        self.assertEqual(await anext(iterator), "é")

    async def test_get_iter_fragmented_binary_message_being_received(self):
        """get_iter yields a fragmented binary message that is partially received."""
        self.assembler.put(Frame(OP_BINARY, b"t", fin=False))
        iterator = aiter(self.assembler.get_iter())
        self.assertEqual(await anext(iterator), b"t")
        self.assembler.put(Frame(OP_CONT, b"e", fin=False))
        self.assertEqual(await anext(iterator), b"e")
        self.assembler.put(Frame(OP_CONT, b"a"))
        self.assertEqual(await anext(iterator), b"a")

    async def test_get_iter_encoded_text_message(self):
        """get_iter yields a text message without UTF-8 decoding."""
        self.assembler.put(Frame(OP_TEXT, b"ca", fin=False))
        self.assembler.put(Frame(OP_CONT, b"f\xc3", fin=False))
        self.assembler.put(Frame(OP_CONT, b"\xa9"))
        fragments = await alist(self.assembler.get_iter(decode=False))
        self.assertEqual(fragments, [b"ca", b"f\xc3", b"\xa9"])

    async def test_get_iter_decoded_binary_message(self):
        """get_iter yields a binary message with UTF-8 decoding."""
        self.assembler.put(Frame(OP_BINARY, b"t", fin=False))
        self.assembler.put(Frame(OP_CONT, b"e", fin=False))
        self.assembler.put(Frame(OP_CONT, b"a"))
        fragments = await alist(self.assembler.get_iter(decode=True))
        self.assertEqual(fragments, ["t", "e", "a"])

    async def test_get_iter_resumes_reading(self):
        """get_iter resumes reading when queue goes below the low-water mark."""
        self.assembler.put(Frame(OP_BINARY, b"t", fin=False))
        self.assembler.put(Frame(OP_CONT, b"e", fin=False))
        self.assembler.put(Frame(OP_CONT, b"a"))

        iterator = aiter(self.assembler.get_iter())

        # queue is above the low-water mark
        await anext(iterator)
        self.resume.assert_not_called()

        # queue is at the low-water mark
        await anext(iterator)
        self.resume.assert_called_once_with()

        # queue is below the low-water mark
        await anext(iterator)
        self.resume.assert_called_once_with()

    async def test_get_iter_does_not_resume_reading(self):
        """get_iter does not resume reading when the low-water mark is unset."""
        self.assembler.low = None

        self.assembler.put(Frame(OP_BINARY, b"t", fin=False))
        self.assembler.put(Frame(OP_CONT, b"e", fin=False))
        self.assembler.put(Frame(OP_CONT, b"a"))
        iterator = aiter(self.assembler.get_iter())
        await anext(iterator)
        await anext(iterator)
        await anext(iterator)

        self.resume.assert_not_called()

    async def test_cancel_get_iter_before_first_frame(self):
        """get_iter can be canceled safely before reading the first frame."""
        getter_task = asyncio.create_task(alist(self.assembler.get_iter()))
        await asyncio.sleep(0)  # let the event loop start getter_task
        getter_task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await getter_task

        self.assembler.put(Frame(OP_TEXT, b"caf\xc3\xa9"))

        fragments = await alist(self.assembler.get_iter())
        self.assertEqual(fragments, ["café"])

    async def test_cancel_get_iter_after_first_frame(self):
        """get_iter cannot be canceled after reading the first frame."""
        self.assembler.put(Frame(OP_TEXT, b"ca", fin=False))

        getter_task = asyncio.create_task(alist(self.assembler.get_iter()))
        await asyncio.sleep(0)  # let the event loop start getter_task
        getter_task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await getter_task

        self.assembler.put(Frame(OP_CONT, b"f\xc3", fin=False))
        self.assembler.put(Frame(OP_CONT, b"\xa9"))

        with self.assertRaises(ConcurrencyError):
            await alist(self.assembler.get_iter())

    # Test put

    async def test_put_pauses_reading(self):
        """put pauses reading when queue goes above the high-water mark."""
        # queue is below the high-water mark
        self.assembler.put(Frame(OP_TEXT, b"caf\xc3\xa9"))
        self.assembler.put(Frame(OP_BINARY, b"t", fin=False))
        self.pause.assert_not_called()

        # queue is at the high-water mark
        self.assembler.put(Frame(OP_CONT, b"e", fin=False))
        self.pause.assert_called_once_with()

        # queue is above the high-water mark
        self.assembler.put(Frame(OP_CONT, b"a"))
        self.pause.assert_called_once_with()

    async def test_put_does_not_pause_reading(self):
        """put does not pause reading when the high-water mark is unset."""
        self.assembler.high = None

        self.assembler.put(Frame(OP_TEXT, b"caf\xc3\xa9"))
        self.assembler.put(Frame(OP_BINARY, b"t", fin=False))
        self.assembler.put(Frame(OP_CONT, b"e", fin=False))
        self.assembler.put(Frame(OP_CONT, b"a"))

        self.pause.assert_not_called()

    # Test termination

    async def test_get_fails_when_interrupted_by_close(self):
        """get raises EOFError when close is called."""
        asyncio.get_running_loop().call_soon(self.assembler.close)
        with self.assertRaises(EOFError):
            await self.assembler.get()

    async def test_get_iter_fails_when_interrupted_by_close(self):
        """get_iter raises EOFError when close is called."""
        asyncio.get_running_loop().call_soon(self.assembler.close)
        with self.assertRaises(EOFError):
            async for _ in self.assembler.get_iter():
                self.fail("no fragment expected")

    async def test_get_fails_after_close(self):
        """get raises EOFError after close is called."""
        self.assembler.close()
        with self.assertRaises(EOFError):
            await self.assembler.get()

    async def test_get_iter_fails_after_close(self):
        """get_iter raises EOFError after close is called."""
        self.assembler.close()
        with self.assertRaises(EOFError):
            async for _ in self.assembler.get_iter():
                self.fail("no fragment expected")

    async def test_get_queued_message_after_close(self):
        """get returns a message after close is called."""
        self.assembler.put(Frame(OP_TEXT, b"caf\xc3\xa9"))
        self.assembler.close()
        message = await self.assembler.get()
        self.assertEqual(message, "café")

    async def test_get_iter_queued_message_after_close(self):
        """get_iter yields a message after close is called."""
        self.assembler.put(Frame(OP_TEXT, b"caf\xc3\xa9"))
        self.assembler.close()
        fragments = await alist(self.assembler.get_iter())
        self.assertEqual(fragments, ["café"])

    async def test_get_queued_fragmented_message_after_close(self):
        """get reassembles a fragmented message after close is called."""
        self.assembler.put(Frame(OP_BINARY, b"t", fin=False))
        self.assembler.put(Frame(OP_CONT, b"e", fin=False))
        self.assembler.put(Frame(OP_CONT, b"a"))
        self.assembler.close()
        self.assembler.close()
        message = await self.assembler.get()
        self.assertEqual(message, b"tea")

    async def test_get_iter_queued_fragmented_message_after_close(self):
        """get_iter yields a fragmented message after close is called."""
        self.assembler.put(Frame(OP_BINARY, b"t", fin=False))
        self.assembler.put(Frame(OP_CONT, b"e", fin=False))
        self.assembler.put(Frame(OP_CONT, b"a"))
        self.assembler.close()
        fragments = await alist(self.assembler.get_iter())
        self.assertEqual(fragments, [b"t", b"e", b"a"])

    async def test_get_partially_queued_fragmented_message_after_close(self):
        """get raises EOF on a partial fragmented message after close is called."""
        self.assembler.put(Frame(OP_BINARY, b"t", fin=False))
        self.assembler.put(Frame(OP_CONT, b"e", fin=False))
        self.assembler.close()
        with self.assertRaises(EOFError):
            await self.assembler.get()

    async def test_get_iter_partially_queued_fragmented_message_after_close(self):
        """get_iter yields a partial fragmented message after close is called."""
        self.assembler.put(Frame(OP_BINARY, b"t", fin=False))
        self.assembler.put(Frame(OP_CONT, b"e", fin=False))
        self.assembler.close()
        fragments = []
        with self.assertRaises(EOFError):
            async for fragment in self.assembler.get_iter():
                fragments.append(fragment)
        self.assertEqual(fragments, [b"t", b"e"])

    async def test_put_fails_after_close(self):
        """put raises EOFError after close is called."""
        self.assembler.close()
        with self.assertRaises(EOFError):
            self.assembler.put(Frame(OP_TEXT, b"caf\xc3\xa9"))

    async def test_close_is_idempotent(self):
        """close can be called multiple times safely."""
        self.assembler.close()
        self.assembler.close()

    # Test (non-)concurrency

    async def test_get_fails_when_get_is_running(self):
        """get cannot be called concurrently."""
        asyncio.create_task(self.assembler.get())
        await asyncio.sleep(0)
        with self.assertRaises(ConcurrencyError):
            await self.assembler.get()
        self.assembler.put(Frame(OP_TEXT, b""))  # let task terminate

    async def test_get_fails_when_get_iter_is_running(self):
        """get cannot be called concurrently with get_iter."""
        asyncio.create_task(alist(self.assembler.get_iter()))
        await asyncio.sleep(0)
        with self.assertRaises(ConcurrencyError):
            await self.assembler.get()
        self.assembler.put(Frame(OP_TEXT, b""))  # let task terminate

    async def test_get_iter_fails_when_get_is_running(self):
        """get_iter cannot be called concurrently with get."""
        asyncio.create_task(self.assembler.get())
        await asyncio.sleep(0)
        with self.assertRaises(ConcurrencyError):
            await alist(self.assembler.get_iter())
        self.assembler.put(Frame(OP_TEXT, b""))  # let task terminate

    async def test_get_iter_fails_when_get_iter_is_running(self):
        """get_iter cannot be called concurrently."""
        asyncio.create_task(alist(self.assembler.get_iter()))
        await asyncio.sleep(0)
        with self.assertRaises(ConcurrencyError):
            await alist(self.assembler.get_iter())
        self.assembler.put(Frame(OP_TEXT, b""))  # let task terminate

    # Test setting limits

    async def test_set_high_water_mark(self):
        """high sets the high-water and low-water marks."""
        assembler = Assembler(high=10)
        self.assertEqual(assembler.high, 10)
        self.assertEqual(assembler.low, 2)

    async def test_set_low_water_mark(self):
        """low sets the low-water and high-water marks."""
        assembler = Assembler(low=5)
        self.assertEqual(assembler.low, 5)
        self.assertEqual(assembler.high, 20)

    async def test_set_high_and_low_water_marks(self):
        """high and low set the high-water and low-water marks."""
        assembler = Assembler(high=10, low=5)
        self.assertEqual(assembler.high, 10)
        self.assertEqual(assembler.low, 5)

    async def test_unset_high_and_low_water_marks(self):
        """High-water and low-water marks are unset."""
        assembler = Assembler()
        self.assertEqual(assembler.high, None)
        self.assertEqual(assembler.low, None)

    async def test_set_invalid_high_water_mark(self):
        """high must be a non-negative integer."""
        with self.assertRaises(ValueError):
            Assembler(high=-1)

    async def test_set_invalid_low_water_mark(self):
        """low must be higher than high."""
        with self.assertRaises(ValueError):
            Assembler(low=10, high=5)
