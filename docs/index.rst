.. module:: websockets

WebSockets
==========

``websockets`` is an implementation of `RFC 6455`_, the WebSocket protocol,
with a focus on simplicity and correctness.

It relies on the `Tulip`_ library, which will become the standard for
`asynchronous I/O`_ in future versions of Python, and requires Python ≥ 3.3.

You can download the code and report issues `on GitHub`_.

.. _RFC 6455: http://tools.ietf.org/html/rfc6455
.. _Tulip: http://code.google.com/p/tulip/
.. _asynchronous I/O: http://www.python.org/dev/peps/pep-3156/
.. _on GitHub: https://github.com/aaugustin/websockets

Example
-------

.. _server-example:

Here's a WebSocket server example. It reads a name from the client and sends a
greeting.

.. literalinclude:: ../example/server.py

.. note::

    The handler function, ``hello``, is executed once for each WebSocket
    connection. The connection is automatically closed when the handler
    returns. If you want to process several messages in the same connection,
    you must write a loop, most likely with :attr:`websocket.open
    <websockets.protocol.WebSocketCommonProtocol.open>`.

.. _client-example:

Here's a corresponding client example.

.. literalinclude:: ../example/client.py

Design
------

``websockets`` provides complete client and server implementations, as shown in
the examples above. These functions are built on top of low-level APIs
reflecting the two phases of the WebSocket protocol:

1. An opening handshake, in the form of an HTTP Upgrade request;
2. Data transfer, as framed messages, ending with a closing handshake.

The first phase is designed to integrate with existing HTTP software.
``websockets`` provides functions to build and validate the request and
response headers.

The second phase is the core of the WebSocket protocol. ``websockets``
provides a standalone implementation on top of Tulip with a very simple API.

For convenience, public APIs can be imported directly from the
:mod:`websockets` package, unless noted otherwise. Anything that isn't listed
in this document is a private API.

High-level API
--------------

Server
......

.. automodule:: websockets.server

   .. autofunction:: serve(ws_handler, host=None, port=None, **kwargs)

   .. autoclass:: WebSocketServerProtocol(self, ws_handler, timeout=10)
        :members: handshake

Client
......

.. automodule:: websockets.client

   .. autofunction:: connect(uri)

   .. autoclass:: WebSocketClientProtocol(self, timeout=10)
        :members: handshake

Shared
......

.. automodule:: websockets.protocol

   .. autoclass:: WebSocketCommonProtocol(self, timeout=10)

        .. autoattribute:: open
        .. automethod:: close(code=1000, reason='')

        .. automethod:: recv()
        .. automethod:: send(data)

        .. automethod:: ping(data=None)
        .. automethod:: pong()

Low-level API
-------------

Exceptions
..........

.. automodule:: websockets.exceptions
   :members:

Opening handshake
.................

.. automodule:: websockets.handshake
   :members:

Data transfer
.............

.. automodule:: websockets.framing
   :members:

URI parser
..........

.. automodule:: websockets.uri
   :members:

Utilities
.........

.. automodule:: websockets.http
   :members:


Limitations
-----------

The following parts of RFC 6455 aren't implemented:

- `Subprotocols`_
- `Extensions`_

.. _Subprotocols: http://tools.ietf.org/html/rfc6455#section-1.9
.. _Extensions: http://tools.ietf.org/html/rfc6455#section-9

License
-------

.. literalinclude:: ../LICENSE
