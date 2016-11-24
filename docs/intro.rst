Getting started
===============

.. warning::

    This documentation is written for Python ≥ 3.5. If you're using Python 3.4
    or 3.3, you will have to :ref:`adapt the code samples <python-lt-35>`.

Basic example
-------------

*This section assumes Python ≥ 3.5. For older versions, read below.*

.. _server-example:

Here's a WebSocket server example. It reads a name from the client, sends a
greeting, and closes the connection.

.. literalinclude:: ../example/server.py

.. _client-example:

On the server side, the handler coroutine ``hello`` is executed once for each
WebSocket connection. The connection is automatically closed when the handler
returns.

Here's a corresponding client example.

.. literalinclude:: ../example/client.py

``async`` and ``await`` aren't available in Python < 3.5. Here's how to adapt
the client example for older Python versions.

.. literalinclude:: ../example/oldclient.py

Browser-based example
---------------------

Here's an example of how to run a WebSocket server and connect from a browser.

Run this script in a console:

.. literalinclude:: ../example/sendtime.py

Then open this HTML file in a browser.

.. literalinclude:: ../example/showtime.html
   :language: html

Common patterns
---------------

You will usually want to process several messages during the lifetime of a
connection. Therefore you must write a loop. Here are the basic patterns for
building a WebSocket server.

Consumer
........

For receiving messages and passing them to a ``consumer`` coroutine::

    async def handler(websocket, path):
        while True:
            message = await websocket.recv()
            await consumer(message)

:meth:`~websockets.protocol.WebSocketCommonProtocol.recv` raises a
:exc:`~websockets.exceptions.ConnectionClosed` exception when the client
disconnects, which breaks out of the ``while True`` loop.

Producer
........

For getting messages from a ``producer`` coroutine and sending them::

    async def handler(websocket, path):
        while True:
            message = await producer()
            await websocket.send(message)

:meth:`~websockets.protocol.WebSocketCommonProtocol.send` raises a
:exc:`~websockets.exceptions.ConnectionClosed` exception when the client
disconnects, which breaks out of the ``while True`` loop.

Both
....

Of course, you can combine the two patterns shown above to read and write
messages on the same connection.

::

    async def consumer_handler(websocket):
        while True:
            message = await websocket.recv()
            await consumer(message)

    async def producer_handler(websocket):
        while True:
            message = await producer()
            await websocket.send(message)

    async def handler(websocket, path):
        consumer_task = asyncio.ensure_future(consumer_handler(websocket))
        producer_task = asyncio.ensure_future(producer_handler(websocket))
        done, pending = await asyncio.wait(
            [consumer_task, producer_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in pending:
            task.cancel()

Registration
............

If you need to maintain a list of currently connected clients, you must
register clients when they connect and unregister them when they disconnect.

::

    connected = set()

    async def handler(websocket, path):
        global connected
        # Register.
        connected.add(websocket)
        try:
            # Implement logic here.
            await asyncio.wait([ws.send("Hello!") for ws in connected])
            await asyncio.sleep(10)
        finally:
            # Unregister.
            connected.remove(websocket)

This simplistic example keeps track of connected clients in memory. This only
works as long as you run a single process. In a practical application, the
handler may subscribe to some channels on a message broker, for example.

That's all!
-----------

The design of the ``websockets`` API was driven by simplicity.

You don't have to worry about performing the opening or the closing handshake,
answering pings, or any other behavior required by the specification.

``websockets`` handles all this under the hood so you don't have to.

.. _python-lt-35:

Python < 3.5
------------

This documentation uses the ``await`` and ``async`` syntax introduced in
Python 3.5.

If you're using Python 3.4 or 3.3, you must substitute::

    async def ...

with::

    @asyncio.coroutine
    def ...

and::

     await ...

with::

    yield from ...

Otherwise you will encounter a :exc:`SyntaxError`.
