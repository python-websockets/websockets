Getting started
===============

.. currentmodule:: websockets

Installation
------------

Install ``websockets`` with::

    pip install websockets

``websockets`` requires Python ≥ 3.4. We recommend using the latest version.

If you're using an older version, be aware that for each minor version (3.x),
only the latest bugfix release (3.x.y) is officially supported.

.. warning::

    This documentation is written for Python ≥ 3.5.1. If you're using an older
    Python version, you need to :ref:`adapt the code samples <python-lt-351>`.

Basic example
-------------

*This section assumes Python ≥ 3.5.1. For older versions, read below.*

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

``async`` and ``await`` were introduced in Python 3.5. websockets supports
+asynchronous context managers on Python ≥ 3.5.1. Here's how to adapt the
client example for older Python versions.

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

    async def consumer_handler(websocket, path):
        async for message in websocket:
            await consumer(message)

Iteration terminates when the client disconnects.

Asynchronous iteration was introduced in Python 3.6; here's the same code for
earlier Python versions::

    async def consumer_handler(websocket, path):
        while True:
            message = await websocket.recv()
            await consumer(message)

:meth:`~protocol.WebSocketCommonProtocol.recv` raises a
:exc:`~exceptions.ConnectionClosed` exception when the client disconnects,
which breaks out of the ``while True`` loop.

Producer
........

For getting messages from a ``producer`` coroutine and sending them::

    async def producer_handler(websocket, path):
        while True:
            message = await producer()
            await websocket.send(message)

:meth:`~protocol.WebSocketCommonProtocol.send` raises a
:exc:`~exceptions.ConnectionClosed` exception when the client disconnects,
which breaks out of the ``while True`` loop.

Both
....

You can read and write messages on the same connection by combining the two
patterns shown above and running the two tasks in parallel::

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

.. _python-lt-351:

Python < 3.5.1
--------------

This documentation uses the ``await`` and ``async`` syntax introduced in
Python 3.5.

If you're using Python < 3.5, you must substitute::

    async def ...

with::

    @asyncio.coroutine
    def ...

and::

     await ...

with::

    yield from ...

Otherwise you will encounter a :exc:`SyntaxError`.

websockets supports asynchronous context managers only on Python ≥ 3.5.1
because :func:`~asyncio.ensure_future` was changed to accept arbitrary
awaitables in that version.

If you're using Python ≤ 3.5, you can't use this feature.
