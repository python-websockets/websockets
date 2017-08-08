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

   .. autofunction:: serve(ws_handler, host=None, port=None, *, create_protocol=None, timeout=10, max_size=2 ** 20, max_queue=2 ** 5, read_limit=2 ** 16, write_limit=2 ** 16, loop=None, origins=None, subprotocols=None, extra_headers=None, **kwds)

   .. autoclass:: WebSocketServer

        .. automethod:: close()
        .. automethod:: wait_closed()

   .. autoclass:: WebSocketServerProtocol(ws_handler, ws_server, *, host=None, port=None, secure=None, timeout=10, max_size=2 ** 20, max_queue=2 ** 5, read_limit=2 ** 16, write_limit=2 ** 16, loop=None, origins=None, subprotocols=None, extra_headers=None)

        .. automethod:: handshake(origins=None, subprotocols=None, extra_headers=None)
        .. automethod:: select_subprotocol(client_protos, server_protos)
        .. automethod:: get_response_status(set_header)

.. _custom-handling:

Customizing Request Handling
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

To set additional response headers or to selectively bypass the handshake,
you can subclass :class:`~websockets.server.WebSocketServerProtocol`,
override the
:meth:`~websockets.server.WebSocketServerProtocol.get_response_status`
method, and pass the class to :func:`~websockets.server.serve()` via the
``create_protocol`` keyword argument.

If :meth:`~websockets.server.WebSocketServerProtocol.get_response_status`
returns a status code other than the default of
``HTTPStatus.SWITCHING_PROTOCOLS``, the
:class:`~websockets.server.WebSocketServerProtocol` object will close the
connection immediately and respond with that status code.

For example, the request headers can be examined and the request
authenticated to decide whether to return ``HTTPStatus.UNAUTHORIZED`` or
``HTTPStatus.FORBIDDEN``. Similarly, the current request path can be
examined to check for ``HTTPStatus.NOT_FOUND``.

The following instance attributes are guaranteed to be available from
within this method:

* ``origin``
* ``path``
* ``raw_request_headers``
* ``request_headers``

The ``set_header(key, value)`` function, which is provided as an argument to
``get_response_status()``, can be used to set additional response headers,
regardless of whether the handshake is aborted.

Client
......

.. automodule:: websockets.client

   .. autofunction:: connect(uri, *, create_protocol=None, timeout=10, max_size=2 ** 20, max_queue=2 ** 5, read_limit=2 ** 16, write_limit=2 ** 16, loop=None, origin=None, subprotocols=None, extra_headers=None, **kwds)

   .. autoclass:: WebSocketClientProtocol(*, host=None, port=None, secure=None, timeout=10, max_size=2 ** 20, max_queue=2 ** 5, read_limit=2 ** 16, write_limit=2 ** 16, loop=None)

        .. automethod:: handshake(wsuri, origin=None, subprotocols=None, extra_headers=None)

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
