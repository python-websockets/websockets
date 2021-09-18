Getting started
===============

.. currentmodule:: websockets

Requirements
------------

websockets requires Python ≥ 3.7.

.. admonition:: Use the most recent Python release
    :class: tip

    For each minor version (3.x), only the latest bugfix or security release
    (3.x.y) is officially supported.

Installation
------------

Install websockets with::

    pip install websockets

Basic example
-------------

.. _server-example:

Here's a WebSocket server example.

It reads a name from the client, sends a greeting, and closes the connection.

.. literalinclude:: ../../example/server.py
    :emphasize-lines: 8,18

.. _client-example:

On the server side, websockets executes the handler coroutine ``hello()`` once
for each WebSocket connection. It closes the connection when the handler
coroutine returns.

Here's a corresponding WebSocket client example.

.. literalinclude:: ../../example/client.py
    :emphasize-lines: 10

Using :func:`~client.connect` as an asynchronous context manager ensures the
connection is closed before exiting the ``hello()`` coroutine.

.. _secure-server-example:

Secure example
--------------

Secure WebSocket connections improve confidentiality and also reliability
because they reduce the risk of interference by bad proxies.

The ``wss`` protocol is to ``ws`` what ``https`` is to ``http``. The
connection is encrypted with TLS_ (Transport Layer Security). ``wss``
requires certificates like ``https``.

.. _TLS: https://developer.mozilla.org/en-US/docs/Web/Security/Transport_Layer_Security

.. admonition:: TLS vs. SSL
    :class: tip

    TLS is sometimes referred to as SSL (Secure Sockets Layer). SSL was an
    earlier encryption protocol; the name stuck.

Here's how to adapt the server example to provide secure connections. See the
documentation of the :mod:`ssl` module for configuring the context securely.

.. literalinclude:: ../../example/secure_server.py
    :emphasize-lines: 19-21,24

Here's how to adapt the client.

.. literalinclude:: ../../example/secure_client.py
    :emphasize-lines: 10-12,16

This client needs a context because the server uses a self-signed certificate.

A client connecting to a secure WebSocket server with a valid certificate
(i.e. signed by a CA that your Python installation trusts) can simply pass
``ssl=True`` to :func:`~client.connect` instead of building a context.

Browser-based example
---------------------

Here's an example of how to run a WebSocket server and connect from a browser.

Run this script in a console:

.. literalinclude:: ../../example/show_time.py

Then open this HTML file in a browser.

.. literalinclude:: ../../example/show_time.html
   :language: html

Synchronization example
-----------------------

A WebSocket server can receive events from clients, process them to update the
application state, and synchronize the resulting state across clients.

Here's an example where any client can increment or decrement a counter.
Updates are propagated to all connected clients.

The concurrency model of :mod:`asyncio` guarantees that updates are
serialized.

Run this script in a console:

.. literalinclude:: ../../example/counter.py

Then open this HTML file in several browsers.

.. literalinclude:: ../../example/counter.html
   :language: html

Common patterns
---------------

You will usually want to process several messages during the lifetime of a
connection. Therefore you must write a loop. Here are the basic patterns for
building a WebSocket server.

Consumer
........

For receiving messages and passing them to a ``consumer`` coroutine::

    async def consumer_handler(websocket):
        async for message in websocket:
            await consumer(message)

In this example, ``consumer`` represents your business logic for processing
messages received on the WebSocket connection.

Iteration terminates when the client disconnects.

Producer
........

For getting messages from a ``producer`` coroutine and sending them::

    async def producer_handler(websocket):
        while True:
            message = await producer()
            await websocket.send(message)

In this example, ``producer`` represents your business logic for generating
messages to send on the WebSocket connection.

:meth:`~legacy.protocol.WebSocketCommonProtocol.send` raises a
:exc:`~exceptions.ConnectionClosed` exception when the client disconnects,
which breaks out of the ``while True`` loop.

Both sides
..........

You can read and write messages on the same connection by combining the two
patterns shown above and running the two tasks in parallel::

    async def handler(websocket):
        consumer_task = asyncio.ensure_future(
            consumer_handler(websocket))
        producer_task = asyncio.ensure_future(
            producer_handler(websocket))
        done, pending = await asyncio.wait(
            [consumer_task, producer_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()

Registration
............

As shown in the synchronization example above, if you need to maintain a list
of currently connected clients, you must register them when they connect and
unregister them when they disconnect.

::

    connected = set()

    async def handler(websocket):
        # Register.
        connected.add(websocket)
        try:
            # Broadcast a message to all connected clients.
            websockets.broadcast(connected, "Hello!")
            await asyncio.sleep(10)
        finally:
            # Unregister.
            connected.remove(websocket)

This simplistic example keeps track of connected clients in memory. This only
works as long as you run a single process. In a practical application, the
handler may subscribe to some channels on a message broker, for example.

That's all!
-----------

The design of the websockets API was driven by simplicity.

You don't have to worry about performing the opening or the closing handshake,
answering pings, or any other behavior required by the specification.

websockets handles all this under the hood so you don't have to.
