from __future__ import annotations

import asyncio
import codecs
import collections
from typing import (
    Any,
    AsyncIterator,
    Callable,
    Generic,
    Optional,
    Tuple,
    TypeVar,
)

from ..frames import OP_BINARY, OP_CONT, OP_TEXT, Frame
from ..typing import Data


__all__ = ["Assembler"]

UTF8Decoder = codecs.getincrementaldecoder("utf-8")

T = TypeVar("T")


class SimpleQueue(Generic[T]):
    """
    Simplified version of asyncio.Queue.

    Doesn't support maxsize nor concurrent calls to get().

    """

    def __init__(self) -> None:
        self.loop = asyncio.get_running_loop()
        self.get_waiter: Optional[asyncio.Future[None]] = None
        self.queue: collections.deque[T] = collections.deque()

    def __len__(self) -> int:
        return len(self.queue)

    def put(self, item: T) -> None:
        """Put an item into the queue without waiting."""
        self.queue.append(item)
        if self.get_waiter is not None and not self.get_waiter.done():
            self.get_waiter.set_result(None)

    async def get(self) -> T:
        """Remove and return an item from the queue, waiting if necessary."""
        if not self.queue:
            if self.get_waiter is not None:
                raise RuntimeError("get is already running")
            self.get_waiter = self.loop.create_future()
            try:
                await self.get_waiter
            finally:
                self.get_waiter.cancel()
                self.get_waiter = None
        return self.queue.popleft()

    def abort(self) -> None:
        if self.get_waiter is not None and not self.get_waiter.done():
            self.get_waiter.set_exception(EOFError("stream of frames ended"))


class Assembler:
    """
    Assemble messages from frames.

    :class:`Assembler` expects only data frames. The stream of frames must
    respect the protocol; if it doesn't, the behavior is undefined.

    Args:
        pause: Called when the buffer of frames goes above the high water mark;
            should pause reading from the network.
        resume: Called when the buffer of frames goes below the low water mark;
            should resume reading from the network.

    """

    def __init__(
        self,
        pause: Callable[[], Any] = lambda: None,
        resume: Callable[[], Any] = lambda: None,
    ) -> None:
        # Queue of incoming messages. Each item is a queue of frames.
        self.frames: SimpleQueue[Frame] = SimpleQueue()

        # We cannot put a hard limit on the size of the queues because a single
        # call to Protocol.data_received() could produce thousands of frames,
        # which must be buffered. Instead, we pause reading when the buffer goes
        # above the high limit and we resume when it goes under the low limit.
        self.high = 16
        self.low = 4
        self.paused = False
        self.pause = pause
        self.resume = resume

        # This flag prevents concurrent calls to get() by user code.
        self.get_in_progress = False

        # This flag marks the end of the connection.
        self.closed = False

    async def get(self, decode: Optional[bool] = None) -> Data:
        """
        Read the next message.

        :meth:`get` returns a single :class:`str` or :class:`bytes`.

        If the message is fragmented, :meth:`get` waits until the last frame is
        received, then it reassembles the message and returns it. To receive
        messages frame by frame, use :meth:`get_iter` instead.

        Raises:
            EOFError: If the stream of frames has ended.
            RuntimeError: If two coroutines run :meth:`get` or :meth:`get_iter`
                concurrently.

        """
        if self.closed:
            raise EOFError("stream of frames ended")

        if self.get_in_progress:
            raise RuntimeError("get or get_iter is already running")

        # Locking with get_in_progress ensures only one coroutine can get here.
        self.get_in_progress = True
        try:
            # First frame
            frame = await self.frames.get()
            self.maybe_resume()
            assert frame.opcode is OP_TEXT or frame.opcode is OP_BINARY
            if decode is None:
                decode = frame.opcode is OP_TEXT
            frames = [frame]
            # Following frames, for fragmented messages
            while not frame.fin:
                frame = await self.frames.get()
                self.maybe_resume()
                assert frame.opcode is OP_CONT
                frames.append(frame)
        finally:
            self.get_in_progress = False

        data = b"".join(frame.data for frame in frames)
        if decode:
            return data.decode()
        else:
            return data

    async def get_iter(self, decode: Optional[bool] = None) -> AsyncIterator[Data]:
        """
        Stream the next message.

        Iterating the return value of :meth:`get_iter` asynchronously yields a
        :class:`str` or :class:`bytes` for each frame in the message.

        The iterator must be fully consumed before calling :meth:`get_iter` or
        :meth:`get` again. Else, :exc:`RuntimeError` is raised.

        This method only makes sense for fragmented messages. If messages aren't
        fragmented, use :meth:`get` instead.

        Raises:
            EOFError: If the stream of frames has ended.
            RuntimeError: If two coroutines run :meth:`get` or :meth:`get_iter`
                concurrently.

        """
        if self.closed:
            raise EOFError("stream of frames ended")

        if self.get_in_progress:
            raise RuntimeError("get or get_iter is already running")

        # Locking with get_in_progress ensures only one coroutine can get here.
        self.get_in_progress = True
        try:
            # First frame
            frame = await self.frames.get()
            self.maybe_resume()
            assert frame.opcode is OP_TEXT or frame.opcode is OP_BINARY
            if decode is None:
                decode = frame.opcode is OP_TEXT
            if decode:
                decoder = UTF8Decoder()
                yield decoder.decode(frame.data, frame.fin)
            else:
                yield frame.data
            # Following frames, for fragmented messages
            while not frame.fin:
                frame = await self.frames.get()
                self.maybe_resume()
                assert frame.opcode is OP_CONT
                if decode:
                    yield decoder.decode(frame.data, frame.fin)
                else:
                    yield frame.data
        finally:
            self.get_in_progress = False

    def put(self, frame: Frame) -> None:
        """
        Add ``frame`` to the next message.

        Raises:
            EOFError: If the stream of frames has ended.

        """
        if self.closed:
            raise EOFError("stream of frames ended")

        self.frames.put(frame)
        self.maybe_pause()

    def get_limits(self) -> Tuple[int, int]:
        """Return low and high water marks for flow control."""
        return self.low, self.high

    def set_limits(self, low: int = 4, high: int = 16) -> None:
        """Configure low and high water marks for flow control."""
        self.low, self.high = low, high

    def maybe_pause(self) -> None:
        """Pause the writer if queue is above the high water mark."""
        # Check for "> high" to support high = 0
        if len(self.frames) > self.high and not self.paused:
            self.paused = True
            self.pause()

    def maybe_resume(self) -> None:
        """Resume the writer if queue is below the low water mark."""
        # Check for "<= low" to support low = 0
        if len(self.frames) <= self.low and self.paused:
            self.paused = False
            self.resume()

    def close(self) -> None:
        """
        End the stream of frames.

        Callling :meth:`close` concurrently with :meth:`get`, :meth:`get_iter`,
        or :meth:`put` is safe. They will raise :exc:`EOFError`.

        """
        if self.closed:
            return

        self.closed = True

        # Unblock get or get_iter.
        self.frames.abort()
