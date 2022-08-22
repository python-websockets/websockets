asyncio usage
=============

.. currentmodule:: websockets

How do I run two coroutines in parallel?
----------------------------------------

You must start two tasks, which the event loop will run concurrently. You can
achieve this with :func:`asyncio.gather` or :func:`asyncio.create_task`.

Keep track of the tasks and make sure they terminate or you cancel them when
the connection terminates.

Why does my program never receive any messages?
-----------------------------------------------

Your program runs a coroutine that never yields control to the event loop. The
coroutine that receives messages never gets a chance to run.

Putting an ``await`` statement in a ``for`` or a ``while`` loop isn't enough
to yield control. Awaiting a coroutine may yield control, but there's no
guarantee that it will.

For example, :meth:`~legacy.protocol.WebSocketCommonProtocol.send` only yields
control when send buffers are full, which never happens in most practical
cases.

If you run a loop that contains only synchronous operations and
a :meth:`~legacy.protocol.WebSocketCommonProtocol.send` call, you must yield
control explicitly with :func:`asyncio.sleep`::

    async def producer(websocket):
        message = generate_next_message()
        await websocket.send(message)
        await asyncio.sleep(0)  # yield control to the event loop

:func:`asyncio.sleep` always suspends the current task, allowing other tasks
to run. This behavior is documented precisely because it isn't expected from
every coroutine.

See `issue 867`_.

.. _issue 867: https://github.com/aaugustin/websockets/issues/867

Why am I having problems with threads?
--------------------------------------

You shouldn't use threads. Use tasks instead.

Indeed, when you chose websockets, you chose :mod:`asyncio` as the primary
framework to handle concurrency. This choice is mutually exclusive with
:mod:`threading`.

If you believe that you need to run websockets in a thread and some logic in
another thread, you should run that logic in a :class:`~asyncio.Task` instead.

If you believe that you cannot run that logic in the same event loop because it
will block websockets, :meth:`~asyncio.loop.run_in_executor` may help.

This question is really about :mod:`asyncio`. Please review the advice about
:ref:`asyncio-multithreading` in the Python documentation.

Why does my simple program misbehave mysteriously?
--------------------------------------------------

You are using :func:`time.sleep` instead of :func:`asyncio.sleep`, which
blocks the event loop and prevents asyncio from operating normally.

This may lead to messages getting send but not received, to connection
timeouts, and to unexpected results of shotgun debugging e.g. adding an
unnecessary call to :meth:`~legacy.protocol.WebSocketCommonProtocol.send`
makes the program functional.