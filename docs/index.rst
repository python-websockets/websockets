.. module:: websockets

WebSockets
==========

``websockets`` is a library for developing WebSocket servers_ and clients_ in
Python. It implements `RFC 6455`_ with a focus on correctness and simplicity.
It passes the `Autobahn Testsuite`_.

Built on top on Python's asynchronous I/O support introduced in `PEP 3156`_,
it provides an API based on coroutines, making it easy to write highly
concurrent applications.

Installation is as simple as ``pip install websockets``. It requires Python ≥
3.4 or Python 3.3 with the ``asyncio`` module, which is available with ``pip
install asyncio`` or in the `Tulip`_ repository.

Bug reports, patches and suggestions welcome! Just open an issue_ or send a
`pull request`_.

.. _servers: https://github.com/aaugustin/websockets/blob/master/example/server.py
.. _clients: https://github.com/aaugustin/websockets/blob/master/example/client.py
.. _RFC 6455: http://tools.ietf.org/html/rfc6455
.. _Autobahn Testsuite: https://github.com/aaugustin/websockets/blob/master/compliance/README.rst
.. _PEP 3156: http://www.python.org/dev/peps/pep-3156/
.. _Tulip: http://code.google.com/p/tulip/
.. _issue: https://github.com/aaugustin/websockets/issues/new
.. _pull request: https://github.com/aaugustin/websockets/compare/

Example
-------

.. _server-example:

Here's a WebSocket server example. It reads a name from the client and sends a
message.

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
provides a standalone implementation on top of ``asyncio`` with a very simple
API.

For convenience, public APIs can be imported directly from the
:mod:`websockets` package, unless noted otherwise. Anything that isn't listed
in this document is a private API.

High-level API
--------------

Server
......

.. automodule:: websockets.server

   .. autofunction:: serve(ws_handler, host=None, port=None, *, klass=WebSocketServerProtocol, **kwds)

   .. autoclass:: WebSocketServerProtocol(self, ws_handler, timeout=10)
        :members: handshake

Client
......

.. automodule:: websockets.client

   .. autofunction:: connect(uri, *, klass=WebSocketClientProtocol, **kwds)

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

Subprotocols_ and Extensions_ aren't implemented. Few subprotocols and no
extensions are registered_ at the time of writing.

.. _Subprotocols: http://tools.ietf.org/html/rfc6455#section-1.9
.. _Extensions: http://tools.ietf.org/html/rfc6455#section-9
.. _registered: http://www.iana.org/assignments/websocket/websocket.xml

License
-------

.. literalinclude:: ../LICENSE
