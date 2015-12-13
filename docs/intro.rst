Getting started
===============

Basic example
-------------

.. _server-example:

Here's a WebSocket server example. It reads a name from the client, sends a
greeting, and closes the connection.

.. literalinclude:: ../example/server.py

.. _client-example:

Here's a corresponding client example.

.. literalinclude:: ../example/client.py

On the server side, the handler coroutine ``hello`` is executed once for
each WebSocket connection. The connection is automatically closed when the
handler returns.

Browser-based example
---------------------

Here's an example of how to run a WebSocket server and connect from a browser.

Run this script in a console:

.. literalinclude:: ../example/time.py

Then open this HTML file in a browser.

.. literalinclude:: ../example/time.html
   :language: html

Common patterns
---------------

You will usually want to process several messages during the lifetime of a
connection. Therefore you must write a loop. Here are the basic patterns for
building a WebSocket server.

Consumer
........

For receiving messages and passing them to a ``consumer`` coroutine::

    @asyncio.coroutine
    def handler(websocket, path):
        while True:
            message = yield from websocket.recv()
            yield from consumer(message)

:meth:`~websockets.protocol.WebSocketCommonProtocol.recv` raises a
:exc:`~websockets.exceptions.ConnectionClosed` exception when the client
disconnects, which breaks out of the ``while True`` loop.

Producer
........

For getting messages from a ``producer`` coroutine and sending them::

    @asyncio.coroutine
    def handler(websocket, path):
        while True:
            message = yield from producer()
            yield from websocket.send(message)

:meth:`~websockets.protocol.WebSocketCommonProtocol.send` raises a
:exc:`~websockets.exceptions.ConnectionClosed` exception when the client
disconnects, which breaks out of the ``while True`` loop.

Both
....

Of course, you can combine the two patterns shown above to read and write
messages on the same connection.

::

    @asyncio.coroutine
    def handler(websocket, path):
        while True:
            listener_task = asyncio.ensure_future(websocket.recv())
            producer_task = asyncio.ensure_future(producer())
            done, pending = yield from asyncio.wait(
                [listener_task, producer_task],
                return_when=asyncio.FIRST_COMPLETED)

            if listener_task in done:
                message = listener_task.result()
                yield from consumer(message)
            else:
                listener_task.cancel()

            if producer_task in done:
                message = producer_task.result()
                yield from websocket.send(message)
            else:
                producer_task.cancel()

(This code looks convoluted. If you know a more straightforward solution,
please let me know about it!)

Registration
............

If you need to maintain a list of currently connected clients, you must
register clients when they connect and unregister them when they disconnect.

::

    connected = set()

    @asyncio.coroutine
    def handler(websocket, path):
        global connected
        # Register.
        connected.add(websocket)
        try:
            # Implement logic here.
            yield from asyncio.wait(
                [ws.send("Hello!") for ws in connected])
            yield from asyncio.sleep(10)
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
