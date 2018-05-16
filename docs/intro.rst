Getting started
===============

.. currentmodule:: websockets

Requirements
------------

``websockets`` requires Python ≥ 3.4.

You should use the latest version of Python if possible. If you're using an
older version, be aware that for each minor version (3.x), only the latest
bugfix release (3.x.y) is officially supported.

For the best experience, you should start with Python ≥ 3.6. :mod:`asyncio`
received interesting improvements between Python 3.4 and 3.6.

.. warning::

    This documentation is written for Python ≥ 3.6. If you're using an older
    Python version, you need to :ref:`adapt the code samples <python-lt-36>`.

Installation
------------

Install ``websockets`` with::

    pip install websockets

Basic example
-------------

.. _server-example:

Here's a WebSocket server example.

It reads a name from the client, sends a greeting, and closes the connection.

.. literalinclude:: ../example/server.py
    :emphasize-lines: 8,17

.. _client-example:

On the server side, ``websockets`` executes the handler coroutine ``hello``
once for each WebSocket connection. It closes the connection when the handler
coroutine returns.

Here's a corresponding WebSocket client example.

.. literalinclude:: ../example/client.py
    :emphasize-lines: 8-10

Using :func:`connect` as an asynchronous context manager ensures the
connection is closed before exiting the ``hello`` coroutine.

Secure example
--------------

Secure WebSocket connections improve confidentiality and also reliability
because they reduce the risk of interference by bad proxies.

The WSS protocol is to WS what HTTPS is to HTTP: the connection is encrypted
with TLS. WSS requires TLS certificates like HTTPS.

Here's how to adapt the server example to provide secure connections, using
APIs available in Python ≥ 3.6.

Refer to the documentation of the :mod:`ssl` module for configuring the
context securely or adapting the code to older Python versions.

.. literalinclude:: ../example/secure_server.py
    :emphasize-lines: 19,23-24

Here's how to adapt the client, also on Python ≥ 3.6.

.. literalinclude:: ../example/secure_client.py
    :emphasize-lines: 10,15-16

This client needs a context because the server uses a self-signed certificate.

A client connecting to a secure WebSocket server with a valid certificate
(i.e. signed by a CA that your Python installation trusts) can simply pass
``ssl=True`` to :func:`connect`` instead of building a context.

Browser-based example
---------------------

Here's an example of how to run a WebSocket server and connect from a browser.

Run this script in a console:

.. literalinclude:: ../example/show_time.py

Then open this HTML file in a browser.

.. literalinclude:: ../example/show_time.html
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

.. literalinclude:: ../example/counter.py

Then open this HTML file in several browsers.

.. literalinclude:: ../example/counter.html
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

In this example, ``consumer`` represents your business logic for processing
messages received on the WebSocket connection.

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

In this example, ``producer`` represents your business logic for generating
messages to send on the WebSocket connection.

:meth:`~protocol.WebSocketCommonProtocol.send` raises a
:exc:`~exceptions.ConnectionClosed` exception when the client disconnects,
which breaks out of the ``while True`` loop.

Both
....

You can read and write messages on the same connection by combining the two
patterns shown above and running the two tasks in parallel::

    async def handler(websocket, path):
        consumer_task = asyncio.ensure_future(
            consumer_handler(websocket, path))
        producer_task = asyncio.ensure_future(
            producer_handler(websocket, path))
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

    async def handler(websocket, path):
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

.. _python-lt-36:

Python < 3.6
------------

This documentation takes advantage of several features that aren't available
in Python < 3.6:

- ``await`` and ``async`` were added in Python 3.5;
- Asynchronous context managers didn't work well until Python 3.5.1;
- Asynchronous iterators were added in Python 3.6;
- f-strings were introduced in Python 3.6 (this is unrelated to :mod:`asyncio`
  and :mod:`websockets`).

Here's how to adapt the basic server example.

.. literalinclude:: ../example/old_server.py
    :emphasize-lines: 8-9,18

And here's the basic client example.

.. literalinclude:: ../example/old_client.py
    :emphasize-lines: 8-11,13,22-23

``await`` and ``async``
.......................

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

Asynchronous context managers
.............................

Asynchronous context managers were added in Python 3.5. However,
``websockets`` only supports them on Python ≥ 3.5.1, where
:func:`~asyncio.ensure_future` accepts any awaitable.

If you're using Python < 3.5.1, instead of::

    with websockets.connect(...) as client:
        ...

you must write::

    client = yield from websockets.connect(...)
    try:
        ...
    finally:
        yield from client.close()

Asynchronous iterators
......................

If you're using Python < 3.6, you must replace::

    async for message in websocket:
        ...

with::

    while True:
        message = yield from websocket.recv()
        ...

The latter will always raise a :exc:`~exceptions.ConnectionClosed` exception
when the connection is closed, while the former will only raise that exception
if the connection terminates with an error.
