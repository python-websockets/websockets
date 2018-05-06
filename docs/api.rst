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

   .. autofunction:: serve(ws_handler, host=None, port=None, *, create_protocol=None, timeout=10, max_size=2 ** 20, max_queue=2 ** 5, read_limit=2 ** 16, write_limit=2 ** 16, loop=None, origins=None, extensions=None, subprotocols=None, extra_headers=None, compression='deflate', **kwds)

   .. autofunction:: unix_serve(ws_handler, path, *, create_protocol=None, timeout=10, max_size=2 ** 20, max_queue=2 ** 5, read_limit=2 ** 16, write_limit=2 ** 16, loop=None, origins=None, extensions=None, subprotocols=None, extra_headers=None, compression='deflate', **kwds)


   .. autoclass:: WebSocketServer

        .. automethod:: close()
        .. automethod:: wait_closed()
        .. autoattribute:: sockets

   .. autoclass:: WebSocketServerProtocol(ws_handler, ws_server, *, host=None, port=None, secure=None, timeout=10, max_size=2 ** 20, max_queue=2 ** 5, read_limit=2 ** 16, write_limit=2 ** 16, loop=None, origins=None, extensions=None, subprotocols=None, extra_headers=None)

        .. automethod:: handshake(origins=None, available_extensions=None, available_subprotocols=None, extra_headers=None)
        .. automethod:: process_request(path, request_headers)
        .. automethod:: select_subprotocol(client_subprotocols, server_subprotocols)

Client
......

.. automodule:: websockets.client

   .. autofunction:: connect(uri, *, create_protocol=None, timeout=10, max_size=2 ** 20, max_queue=2 ** 5, read_limit=2 ** 16, write_limit=2 ** 16, loop=None, origin=None, extensions=None, subprotocols=None, extra_headers=None, compression='deflate', **kwds)

   .. autoclass:: WebSocketClientProtocol(*, host=None, port=None, secure=None, timeout=10, max_size=2 ** 20, max_queue=2 ** 5, read_limit=2 ** 16, write_limit=2 ** 16, loop=None, origin=None, extensions=None, subprotocols=None, extra_headers=None)

        .. automethod:: handshake(wsuri, origin=None, available_extensions=None, available_subprotocols=None, extra_headers=None)

Shared
......

.. automodule:: websockets.protocol

   .. autoclass:: WebSocketCommonProtocol(*, host=None, port=None, secure=None, timeout=10, max_size=2 ** 20, max_queue=2 ** 5, read_limit=2 ** 16, write_limit=2 ** 16, loop=None)

        .. automethod:: close(code=1000, reason='')

        .. automethod:: recv()
        .. automethod:: send(data)

        .. automethod:: ping(data=None)
        .. automethod:: pong(data=b'')

        .. autoattribute:: local_address
        .. autoattribute:: remote_address

        .. autoattribute:: open
        .. autoattribute:: closed

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

.. automodule:: websockets.headers
   :members:

.. automodule:: websockets.http
   :members:
