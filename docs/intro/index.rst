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
