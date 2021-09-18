Quick start
===========

.. currentmodule:: websockets

Here are a few examples to get you started quickly with websockets.

Hello world!
------------

Here's a WebSocket server.

It receives a name from the client, sends a greeting, and closes the connection.

.. literalinclude:: ../../example/quickstart/server.py

:func:`~server.serve` executes the connection handler coroutine ``hello()``
once for each WebSocket connection. It closes the WebSocket connection when
the handler returns.

Here's a corresponding WebSocket client.

It sends a name to the server, receives a greeting, and closes the connection.

.. literalinclude:: ../../example/quickstart/client.py

Using :func:`~client.connect` as an asynchronous context manager ensures the
WebSocket connection is closed.

.. _secure-server-example:

Encryption
----------

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

Here's how to adapt the server to encrypt connections. See the documentation
of the :mod:`ssl` module for configuring the context securely.

.. literalinclude:: ../../example/quickstart/server_secure.py

Here's how to adapt the client similarly.

.. literalinclude:: ../../example/quickstart/client_secure.py

This client needs a context because the server uses a self-signed certificate.

When connecting to a secure WebSocket server with a valid certificate — any
certificate signed by a CA that your Python installation trusts — you can
simply pass ``ssl=True`` to :func:`~client.connect`.

In a browser
------------

The WebSocket protocol was invented for the web — as the name says!

Here's how to connect to a WebSocket server in a browser.

Run this script in a console:

.. literalinclude:: ../../example/quickstart/show_time.py

Save this file as ``show_time.html``:

.. literalinclude:: ../../example/quickstart/show_time.html
   :language: html

Save this file as ``show_time.js``:

.. literalinclude:: ../../example/quickstart/show_time.js
   :language: js

Then open ``show_time.html`` in a browser and see the clock tick irregularly.

Broadcast
---------

A WebSocket server can receive events from clients, process them to update the
application state, and broadcast the updated state to all connected clients.

Here's an example where any client can increment or decrement a counter. The
concurrency model of :mod:`asyncio` guarantees that updates are serialized.

Run this script in a console:

.. literalinclude:: ../../example/quickstart/counter.py

Save this file as ``counter.html``:

.. literalinclude:: ../../example/quickstart/counter.html
   :language: html

Save this file as ``counter.css``:

.. literalinclude:: ../../example/quickstart/counter.css
   :language: css

Save this file as ``counter.js``:

.. literalinclude:: ../../example/quickstart/counter.js
   :language: js

Then open ``counter.html`` file in several browsers and play with [+] and [-].
