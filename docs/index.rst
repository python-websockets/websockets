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

.. _client-example:

Here's a corresponding client example.

.. literalinclude:: ../example/client.py

.. note::

    On the server side, the handler coroutine ``hello`` is executed once for
    each WebSocket connection. The connection is automatically closed when the
    handler returns.

    You will almost always want to process several messages during the
    lifetime of a connection. Therefore you must write a loop. Here are the
    recommended patterns to exit cleanly when the connection drops, either
    because the other side closed it or for any other reason.

    For receiving messages and passing them to a ``consumer`` coroutine::

        @asyncio.coroutine
        def handler(websocket, path):
            while True:
                message = yield from websocket.recv()
                if message is None:
                    break
                yield from consumer(message)

    :meth:`~websockets.protocol.WebSocketCommonProtocol.recv` returns ``None``
    when the connection is closed. In other words, ``None`` marks the end of
    the message stream. The handler coroutine should check for that case and
    return when it happens.

    For getting messages from a ``producer`` coroutine and sending them::

        @asyncio.coroutine
        def handler(websocket, path):
            while True:
                message = yield from producer()
                if not websocket.open:
                    break
                yield from websocket.send(message)

    :meth:`~websockets.protocol.WebSocketCommonProtocol.send` fails with an
    exception when it's called on a closed connection. Therefore the handler
    coroutine should check that the connection is still open before attempting
    to write and return otherwise.

    Of course, you can combine the two patterns shown above to read and write
    messages on the same connection.

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

   .. autofunction:: serve(ws_handler, host=None, port=None, *, loop=None, klass=WebSocketServerProtocol, origins=None, subprotocols=None, **kwds)

   .. autoclass:: WebSocketServerProtocol(ws_handler, *, origins=None, host=None, port=None, secure=None, timeout=10, max_size=2 ** 20, loop=None)
        :members: handshake, select_subprotocol

Client
......

.. automodule:: websockets.client

   .. autofunction:: connect(uri, *, loop=None, klass=WebSocketClientProtocol, origin=None, subprotocols=None, **kwds)

   .. autoclass:: WebSocketClientProtocol(*, host=None, port=None, secure=None, timeout=10, max_size=2 ** 20, loop=None)
        :members: handshake

Shared
......

.. automodule:: websockets.protocol

   .. autoclass:: WebSocketCommonProtocol(*, host=None, port=None, secure=None, timeout=10, max_size=2 ** 20, loop=None)

        .. autoattribute:: open
        .. automethod:: close(code=1000, reason='')

        .. automethod:: recv()
        .. automethod:: send(data)

        .. automethod:: ping(data=None)
        .. automethod:: pong(data=b'')

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

Changelog
---------

2.4
...

* Added support for subprotocols.
* Supported non-default event loop.
* Added `loop` argument to :func:`~websockets.client.connect` and
  :func:`~websockets.server.serve`.

2.3
...

* Improved compliance of close codes.

2.2
...

* Added support for limiting message size.

2.1
...

* Added `host`, `port` and `secure` attributes on protocols.
* Added support for providing and checking Origin_.

.. _Origin: https://tools.ietf.org/html/rfc6455#section-10.2

2.0
...

* Backwards-incompatible API change:
  :meth:`~websockets.protocol.WebSocketCommonProtocol.send`,
  :meth:`~websockets.protocol.WebSocketCommonProtocol.ping` and
  :meth:`~websockets.protocol.WebSocketCommonProtocol.pong` are coroutines.
  They used to be regular functions.
* Add flow control.

1.0
...

* Initial public release.

Limitations
-----------

Extensions_ aren't implemented. No extensions are registered_ at the time of
writing.

.. _Extensions: http://tools.ietf.org/html/rfc6455#section-9
.. _registered: http://www.iana.org/assignments/websocket/websocket.xml

License
-------

.. literalinclude:: ../LICENSE
