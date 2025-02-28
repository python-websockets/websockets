Design a WebSocket application
==============================

.. currentmodule:: websockets

WebSocket server or client applications follow common patterns. This guide
describes patterns that you're likely to implement in your application.

All examples are connection handlers for a server. However, they would also
apply to a client, assuming that ``websocket`` is a connection created with
:func:`~asyncio.client.connect`.

.. admonition:: WebSocket connections are long-lived.
    :class: tip

    You need a loop to process several messages during the lifetime of a
    connection.

Consumer pattern
----------------

To receive messages from the WebSocket connection::

    async def consumer_handler(websocket):
        async for message in websocket:
            await consume(message)

In this example, ``consume()`` is a coroutine implementing your business logic
for processing a message received on the WebSocket connection.

Iteration terminates when the client disconnects.

Producer pattern
----------------

To send messages to the WebSocket connection::

    from websockets.exceptions import ConnectionClosed

    async def producer_handler(websocket):
        while True:
            try:
                message = await produce()
                await websocket.send(message)
            except ConnectionClosed:
                break

In this example, ``produce()`` is a coroutine implementing your business logic
for generating the next message to send on the WebSocket connection.

Iteration terminates when the client disconnects because
:meth:`~asyncio.server.ServerConnection.send` raises a
:exc:`~exceptions.ConnectionClosed` exception, which breaks out of the ``while
True`` loop.

Consumer and producer
---------------------

You can receive and send messages on the same WebSocket connection by
combining the consumer and producer patterns.

This requires running two tasks in parallel. The simplest option offered by
:mod:`asyncio` is::

    import asyncio

    async def handler(websocket):
        await asyncio.gather(
            consumer_handler(websocket),
            producer_handler(websocket),
        )

If a task terminates, :func:`~asyncio.gather` doesn't cancel the other task.
This can result in a situation where the producer keeps running after the
consumer finished, which may leak resources.

Here's a way to exit and close the WebSocket connection as soon as a task
terminates, after canceling the other task::

    async def handler(websocket):
        consumer_task = asyncio.create_task(consumer_handler(websocket))
        producer_task = asyncio.create_task(producer_handler(websocket))
        done, pending = await asyncio.wait(
            [consumer_task, producer_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()

Registration
------------

To keep track of currently connected clients, you can register them when they
connect and unregister them when they disconnect::

    connected = set()

    async def handler(websocket):
        # Register.
        connected.add(websocket)
        try:
            # Broadcast a message to all connected clients.
            broadcast(connected, "Hello!")
            await asyncio.sleep(10)
        finally:
            # Unregister.
            connected.remove(websocket)

This example maintains the set of connected clients in memory. This works as
long as you run a single process. It doesn't scale to multiple processes.

If you just need the set of connected clients, as in this example, use the
:attr:`~asyncio.server.Server.connections` property of the server. This pattern
is needed only when recording additional information about each client.

Publish–subscribe
-----------------

If you plan to run multiple processes and you want to communicate updates
between processes, then you must deploy a messaging system. You may find
publish-subscribe functionality useful.

A complete implementation of this idea with Redis is described in
the :doc:`Django integration guide <../howto/django>`.
