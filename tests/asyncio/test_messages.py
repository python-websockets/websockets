import asyncio
import unittest
import unittest.mock

from websockets.asyncio.messages import *
from websockets.asyncio.messages import SimpleQueue
from websockets.frames import OP_BINARY, OP_CONT, OP_TEXT, Frame


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

    async def test_get_concurrently(self):
        """get cannot be called concurrently with itself."""
        getter_task = asyncio.create_task(self.queue.get())
        await asyncio.sleep(0)  # let the task start
        with self.assertRaises(RuntimeError):
            await self.queue.get()
        getter_task.cancel()


class AssemblerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.pause = unittest.mock.Mock()
        self.resume = unittest.mock.Mock()
        self.assembler = Assembler(pause=self.pause, resume=self.resume)
        self.assembler.set_limits(low=1, high=2)

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
        self.assembler.put(Frame(OP_TEXT, b"caf\xc3\xa9"))
        message = await getter_task
        self.assertEqual(message, "café")

    async def test_get_binary_message_not_received_yet(self):
        """get returns a binary message when it is received."""
        getter_task = asyncio.create_task(self.assembler.get())
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
        """get resumes reading when queue goes below the high-water mark."""
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

    # Test get_iter

    async def run_get_iter(self, **kwargs):
        self.fragments = []
        async for fragment in self.assembler.get_iter(**kwargs):
            self.fragments.append(fragment)

    async def test_get_iter_text_message_already_received(self):
        """get_iter yields a text message that is already received."""
        self.assembler.put(Frame(OP_TEXT, b"caf\xc3\xa9"))
        await self.run_get_iter()
        self.assertEqual(self.fragments, ["café"])

    async def test_get_iter_binary_message_already_received(self):
        """get_iter yields a binary message that is already received."""
        self.assembler.put(Frame(OP_BINARY, b"tea"))
        await self.run_get_iter()
        self.assertEqual(self.fragments, [b"tea"])

    async def test_get_iter_text_message_not_received_yet(self):
        """get_iter yields a text message when it is received."""
        asyncio.create_task(self.run_get_iter())
        self.assembler.put(Frame(OP_TEXT, b"caf\xc3\xa9"))
        await asyncio.sleep(0)  # let run_get_iter() run
        self.assertEqual(self.fragments, ["café"])

    async def test_get_iter_binary_message_not_received_yet(self):
        """get_iter yields a binary message when it is received."""
        asyncio.create_task(self.run_get_iter())
        self.assembler.put(Frame(OP_BINARY, b"tea"))
        await asyncio.sleep(0)  # let run_get_iter() run
        self.assertEqual(self.fragments, [b"tea"])

    async def test_get_iter_fragmented_text_message_already_received(self):
        """get_iter yields a fragmented text message that is already received."""
        self.assembler.put(Frame(OP_TEXT, b"ca", fin=False))
        self.assembler.put(Frame(OP_CONT, b"f\xc3", fin=False))
        self.assembler.put(Frame(OP_CONT, b"\xa9"))
        await self.run_get_iter()
        self.assertEqual(self.fragments, ["ca", "f", "é"])

    async def test_get_iter_fragmented_binary_message_already_received(self):
        """get_iter yields a fragmented binary message that is already received."""
        self.assembler.put(Frame(OP_BINARY, b"t", fin=False))
        self.assembler.put(Frame(OP_CONT, b"e", fin=False))
        self.assembler.put(Frame(OP_CONT, b"a"))
        await self.run_get_iter()
        self.assertEqual(self.fragments, [b"t", b"e", b"a"])

    async def test_get_iter_fragmented_text_message_not_received_yet(self):
        """get_iter yields a fragmented text message when it is received."""
        asyncio.create_task(self.run_get_iter())
        self.assembler.put(Frame(OP_TEXT, b"ca", fin=False))
        await asyncio.sleep(0)  # let run_get_iter() run
        self.assertEqual(self.fragments, ["ca"])
        self.assembler.put(Frame(OP_CONT, b"f\xc3", fin=False))
        await asyncio.sleep(0)  # let run_get_iter() run
        self.assertEqual(self.fragments, ["ca", "f"])
        self.assembler.put(Frame(OP_CONT, b"\xa9"))
        await asyncio.sleep(0)  # let run_get_iter() run
        self.assertEqual(self.fragments, ["ca", "f", "é"])

    async def test_get_iter_fragmented_binary_message_not_received_yet(self):
        """get_iter yields a fragmented binary message when it is received."""
        asyncio.create_task(self.run_get_iter())
        self.assembler.put(Frame(OP_BINARY, b"t", fin=False))
        await asyncio.sleep(0)  # let run_get_iter() run
        self.assertEqual(self.fragments, [b"t"])
        self.assembler.put(Frame(OP_CONT, b"e", fin=False))
        await asyncio.sleep(0)  # let run_get_iter() run
        self.assertEqual(self.fragments, [b"t", b"e"])
        self.assembler.put(Frame(OP_CONT, b"a"))
        await asyncio.sleep(0)  # let run_get_iter() run
        self.assertEqual(self.fragments, [b"t", b"e", b"a"])

    async def test_get_iter_fragmented_text_message_being_received(self):
        """get_iter yields a fragmented text message that is partially received."""
        self.assembler.put(Frame(OP_TEXT, b"ca", fin=False))
        asyncio.create_task(self.run_get_iter())
        await asyncio.sleep(0)  # let run_get_iter() run
        self.assertEqual(self.fragments, ["ca"])
        self.assembler.put(Frame(OP_CONT, b"f\xc3", fin=False))
        await asyncio.sleep(0)  # let run_get_iter() run
        self.assertEqual(self.fragments, ["ca", "f"])
        self.assembler.put(Frame(OP_CONT, b"\xa9"))
        await asyncio.sleep(0)  # let run_get_iter() run
        self.assertEqual(self.fragments, ["ca", "f", "é"])

    async def test_get_iter_fragmented_binary_message_being_received(self):
        """get_iter yields a fragmented binary message that is partially received."""
        self.assembler.put(Frame(OP_BINARY, b"t", fin=False))
        asyncio.create_task(self.run_get_iter())
        await asyncio.sleep(0)  # let run_get_iter() run
        self.assertEqual(self.fragments, [b"t"])
        self.assembler.put(Frame(OP_CONT, b"e", fin=False))
        await asyncio.sleep(0)  # let run_get_iter() run
        self.assertEqual(self.fragments, [b"t", b"e"])
        self.assembler.put(Frame(OP_CONT, b"a"))
        await asyncio.sleep(0)  # let run_get_iter() run
        self.assertEqual(self.fragments, [b"t", b"e", b"a"])

    async def test_get_iter_encoded_text_message(self):
        """get_iter yields a text message without UTF-8 decoding."""
        self.assembler.put(Frame(OP_TEXT, b"ca", fin=False))
        self.assembler.put(Frame(OP_CONT, b"f\xc3", fin=False))
        self.assembler.put(Frame(OP_CONT, b"\xa9"))
        await self.run_get_iter(decode=False)
        self.assertEqual(self.fragments, [b"ca", b"f\xc3", b"\xa9"])

    async def test_get_iter_decoded_binary_message(self):
        """get_iter yields a binary message with UTF-8 decoding."""
        self.assembler.put(Frame(OP_BINARY, b"t", fin=False))
        self.assembler.put(Frame(OP_CONT, b"e", fin=False))
        self.assembler.put(Frame(OP_CONT, b"a"))
        await self.run_get_iter(decode=True)
        self.assertEqual(self.fragments, ["t", "e", "a"])

    async def test_get_iter_resumes_reading(self):
        """get resumes reading when queue goes below the high-water mark."""
        self.assembler.put(Frame(OP_BINARY, b"t", fin=False))
        self.assembler.put(Frame(OP_CONT, b"e", fin=False))
        self.assembler.put(Frame(OP_CONT, b"a"))

        getter_iter = aiter(self.assembler.get_iter())

        # queue is above the low-water mark
        await anext(getter_iter)
        self.resume.assert_not_called()

        # queue is at the low-water mark
        await anext(getter_iter)
        self.resume.assert_called_once_with()

        # queue is below the low-water mark
        await anext(getter_iter)
        self.resume.assert_called_once_with()

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
        """get cannot be called concurrently with itself."""
        asyncio.create_task(self.assembler.get())
        await asyncio.sleep(0)
        with self.assertRaises(RuntimeError):
            await self.assembler.get()
        self.assembler.close()  # let task terminate

    async def test_get_fails_when_get_iter_is_running(self):
        """get cannot be called concurrently with get_iter."""
        asyncio.create_task(self.run_get_iter())
        await asyncio.sleep(0)
        with self.assertRaises(RuntimeError):
            await self.assembler.get()
        self.assembler.close()  # let task terminate

    async def test_get_iter_fails_when_get_is_running(self):
        """get_iter cannot be called concurrently with get."""
        asyncio.create_task(self.assembler.get())
        await asyncio.sleep(0)
        with self.assertRaises(RuntimeError):
            await self.run_get_iter()
        self.assembler.close()  # let task terminate

    async def test_get_iter_fails_when_get_iter_is_running(self):
        """get_iter cannot be called concurrently with itself."""
        asyncio.create_task(self.run_get_iter())
        await asyncio.sleep(0)
        with self.assertRaises(RuntimeError):
            await self.run_get_iter()
        self.assembler.close()  # let task terminate
