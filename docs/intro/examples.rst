Quick examples
==============

.. currentmodule:: websockets

Start a server
--------------

This WebSocket server receives a name from the client, sends a greeting, and
closes the connection.

.. literalinclude:: ../../example/quick/server.py
    :caption: server.py
    :language: python

:func:`~asyncio.server.serve` executes the connection handler coroutine
``hello()`` once for each WebSocket connection. It closes the WebSocket
connection when the handler returns.

Connect a client
----------------

This WebSocket client sends a name to the server, receives a greeting, and
closes the connection.

.. literalinclude:: ../../example/quick/client.py
    :caption: client.py
    :language: python

Using :func:`~sync.client.connect` as a context manager ensures that the
WebSocket connection is closed.

Connect a browser
-----------------

The WebSocket protocol was invented for the web — as the name says!

Here's how to connect a browser to a WebSocket server.

Run this script in a console:

.. literalinclude:: ../../example/quick/show_time.py
    :caption: show_time.py
    :language: python

Save this file as ``show_time.html``:

.. literalinclude:: ../../example/quick/show_time.html
    :caption: show_time.html
    :language: html

Save this file as ``show_time.js``:

.. literalinclude:: ../../example/quick/show_time.js
    :caption: show_time.js
    :language: js

Then, open ``show_time.html`` in several browsers or tabs. Clocks tick
irregularly.

Broadcast messages
------------------

Let's send the same timestamps to everyone instead of generating independent
sequences for each connection.

Stop the previous script if it's still running and run this script in a console:

.. literalinclude:: ../../example/quick/sync_time.py
    :caption: sync_time.py
    :language: python

Refresh ``show_time.html`` in all browsers or tabs. Clocks tick in sync.

Manage application state
------------------------

A WebSocket server can receive events from clients, process them to update the
application state, and broadcast the updated state to all connected clients.

Here's an example where any client can increment or decrement a counter. The
concurrency model of :mod:`asyncio` guarantees that updates are serialized.

This example keep tracks of connected users explicitly in ``USERS`` instead of
relying on :attr:`server.connections <asyncio.server.Server.connections>`. The
result is the same.

Run this script in a console:

.. literalinclude:: ../../example/quick/counter.py
    :caption: counter.py
    :language: python

Save this file as ``counter.html``:

.. literalinclude:: ../../example/quick/counter.html
    :caption: counter.html
    :language: html

Save this file as ``counter.css``:

.. literalinclude:: ../../example/quick/counter.css
    :caption: counter.css
    :language: css

Save this file as ``counter.js``:

.. literalinclude:: ../../example/quick/counter.js
    :caption: counter.js
    :language: js

Then open ``counter.html`` file in several browsers and play with [+] and [-].
