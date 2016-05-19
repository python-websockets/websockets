API
===

Design
------

``websockets`` provides complete client and server implementations, as shown
in the :doc:`getting started guide <intro>`. These functions are built on top
of low-level APIs reflecting the two phases of the WebSocket protocol:

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

High-level
----------

Server
......

.. automodule:: websockets.server

   .. autofunction:: serve(ws_handler, host=None, port=None, *, klass=WebSocketServerProtocol, timeout=10, max_size=2 ** 20, max_queue=2 ** 5, loop=None, origins=None, subprotocols=None, extra_headers=None, **kwds)

   .. autoclass:: WebSocketServerProtocol(ws_handler, ws_server, *, host=None, port=None, secure=None, timeout=10, max_size=2 ** 20, max_queue=2 ** 5, loop=None, origins=None, subprotocols=None, extra_headers=None)

        .. automethod:: handshake(origins=None, subprotocols=None, extra_headers=None)
        .. automethod:: select_subprotocol(client_protos, server_protos)

Client
......

.. automodule:: websockets.client

   .. autofunction:: connect(uri, *, klass=WebSocketClientProtocol, timeout=10, max_size=2 ** 20, max_queue=2 ** 5, loop=None, origin=None, subprotocols=None, extra_headers=None, **kwds)

   .. autoclass:: WebSocketClientProtocol(*, host=None, port=None, secure=None, timeout=10, max_size=2 ** 20, max_queue=2 ** 5, loop=None)

        .. automethod:: handshake(wsuri, origin=None, subprotocols=None, extra_headers=None)

Shared
......

.. automodule:: websockets.protocol

   .. autoclass:: WebSocketCommonProtocol(*, host=None, port=None, secure=None, timeout=10, max_size=2 ** 20, loop=None)

        .. automethod:: close(code=1000, reason='')

        .. automethod:: recv()
        .. automethod:: send(data)

        .. automethod:: ping(data=None)
        .. automethod:: pong(data=b'')

        .. autoattribute:: local_address
        .. autoattribute:: remote_address

        .. autoattribute:: open
        .. autoattribute:: state_name


Exceptions
..........

.. automodule:: websockets.exceptions
   :members:

Low-level
---------

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
