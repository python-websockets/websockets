.. module:: websockets

WebSockets
==========

``websockets`` is a library for developing WebSocket servers_ and clients_ in
Python. It implements `RFC 6455`_ with a focus on correctness and simplicity.
It passes the `Autobahn Testsuite`_.

Built on top of Python's asynchronous I/O support introduced in `PEP 3156`_,
it provides an API based on coroutines, making it easy to write highly
concurrent applications.

Installation is as simple as ``pip install websockets``. It requires Python ≥
3.4 or Python 3.3 with the ``asyncio`` module, which is available with ``pip
install asyncio``.

Bug reports, patches and suggestions welcome! Just open an issue_ or send a
`pull request`_.

.. _servers: https://github.com/aaugustin/websockets/blob/master/example/server.py
.. _clients: https://github.com/aaugustin/websockets/blob/master/example/client.py
.. _RFC 6455: http://tools.ietf.org/html/rfc6455
.. _Autobahn Testsuite: https://github.com/aaugustin/websockets/blob/master/compliance/README.rst
.. _PEP 3156: http://www.python.org/dev/peps/pep-3156/
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
    messages on the same connection::

        @asyncio.coroutine
        def handler(websocket, path):
            while True:
                listener_task = asyncio.ensure_future(websocket.recv())
                producer_task = asyncio.ensure_future(producer())
                done, pending = yield from asyncio.wait(
                    [listener_task, producer_task],
                    return_when=asyncio.FIRST_COMPLETED)

                if listener_task in done:
                    message = listener_task.result()
                    if message is None:
                        break
                    yield from consumer(message)
                else:
                    listener_task.cancel()

                if producer_task in done:
                    message = producer_task.result()
                    if not websocket.open:
                        break
                    yield from websocket.send(message)
                else:
                    producer_task.cancel()

    (This code looks convoluted. If you know a more straightforward solution,
    please let me know about it!)

That's really all you have to know! ``websockets`` manages the connection
under the hood so you don't have to.

Cheat sheet
-----------

Server
......

* Write a coroutine that handles a single connection. It receives a websocket
  protocol instance and the URI path in argument.

  * Call :meth:`~websockets.protocol.WebSocketCommonProtocol.recv` and
    :meth:`~websockets.protocol.WebSocketCommonProtocol.send` to receive and
    send messages at any time.

  * You may :meth:`~websockets.protocol.WebSocketCommonProtocol.ping` or
    :meth:`~websockets.protocol.WebSocketCommonProtocol.pong` if you wish
    but it isn't needed in general.

* Create a server with :func:`~websockets.server.serve` which is similar to
  asyncio's :meth:`~asyncio.BaseEventLoop.create_server`.

  * The server takes care of establishing connections, then lets the handler
    execute the application logic, and finally closes the connection after
    the handler returns.

  * You may subclass :class:`~websockets.server.WebSocketServerProtocol` and
    pass it in the ``klass`` keyword argument for advanced customization.

Client
......

* Create a server with :func:`~websockets.client.connect` which is similar to
  asyncio's :meth:`~asyncio.BaseEventLoop.create_connection`.

  * You may subclass :class:`~websockets.server.WebSocketClientProtocol` and
    pass it in the ``klass`` keyword argument for advanced customization.

* Call :meth:`~websockets.protocol.WebSocketCommonProtocol.recv` and
  :meth:`~websockets.protocol.WebSocketCommonProtocol.send` to receive and
  send messages at any time.

* You may :meth:`~websockets.protocol.WebSocketCommonProtocol.ping` or
  :meth:`~websockets.protocol.WebSocketCommonProtocol.pong` if you wish but it
  isn't needed in general.

* Call :meth:`~websockets.protocol.WebSocketCommonProtocol.close` to terminate
  the connection.

Debugging
.........

If you don't understand what ``websockets`` is doing, enable logging::

    import logging
    logger = logging.getLogger('websockets')
    logger.setLevel(logging.INFO)
    logger.addHandler(logging.StreamHandler())

The logs contains:

* Exceptions in the connection handler at the ``ERROR`` level
* Exceptions in the opening or closing handshake at the ``INFO`` level
* All frames at the ``DEBUG`` level — this can be very verbose

If you're new to ``asyncio``, you will certainly encounter issues that are
related to asynchronous programming in general rather than to ``websockets``
in particular. Fortunately Python's official documentation provides advice to
`develop with asyncio`_. Check it out: it's invaluable!

.. _develop with asyncio: https://docs.python.org/3/library/asyncio-dev.html

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

   .. autofunction:: serve(ws_handler, host=None, port=None, *, loop=None, klass=WebSocketServerProtocol, origins=None, subprotocols=None, extra_headers=None, **kwds)

   .. autoclass:: WebSocketServerProtocol(ws_handler, ws_server, *, origins=None, subprotocols=None, extra_headers=None, host=None, port=None, secure=None, timeout=10, max_size=2 ** 20, loop=None)

        .. automethod:: handshake(origins=None, subprotocols=None, extra_headers=None)
        .. automethod:: select_subprotocol(client_protos, server_protos)

Client
......

.. automodule:: websockets.client

   .. autofunction:: connect(uri, *, loop=None, klass=WebSocketClientProtocol, origin=None, subprotocols=None, extra_headers=None, **kwds)

   .. autoclass:: WebSocketClientProtocol(*, host=None, port=None, secure=None, timeout=10, max_size=2 ** 20, loop=None)

        .. automethod:: handshake(wsuri, origin=None, subprotocols=None, extra_headers=None)

Shared
......

.. automodule:: websockets.protocol

   .. autoclass:: WebSocketCommonProtocol(*, host=None, port=None, secure=None, timeout=10, max_size=2 ** 20, loop=None)

        .. autoattribute:: local_address
        .. autoattribute:: remote_address

        .. autoattribute:: open
        .. automethod:: close(code=1000, reason='')

        .. automethod:: recv()
        .. automethod:: send(data)

        .. automethod:: ping(data=None)
        .. automethod:: pong(data=b'')

Exceptions
..........

.. automodule:: websockets.exceptions
   :members:

Low-level API
-------------

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

2.6
...

* Added ``local_address`` and ``remote_address`` attributes on protocols.

* Closed open connections with code 1001 when a server shuts down.

* Avoided TCP fragmentation of small frames.

2.5
...

* Improved documentation.

* Provided access to handshake request and response HTTP headers.

* Allowed customizing handshake request and response HTTP headers.

* Supported running on a non-default event loop.

* Returned a 403 error code instead of 400 when the request Origin isn't
  allowed.

* Cancelling :meth:`~websockets.protocol.WebSocketCommonProtocol.recv` no
  longer drops the next message.

* Clarified that the closing handshake can be initiated by the client.

* Set the close status code and reason more consistently.

* Strengthened connection termination by simplifying the implementation.

* Improved tests, added tox configuration, and enforced 100% branch coverage.

2.4
...

* Added support for subprotocols.

* Supported non-default event loop.

* Added ``loop`` argument to :func:`~websockets.client.connect` and
  :func:`~websockets.server.serve`.

2.3
...

* Improved compliance of close codes.

2.2
...

* Added support for limiting message size.

2.1
...

* Added ``host``, ``port`` and ``secure`` attributes on protocols.

* Added support for providing and checking Origin_.

.. _Origin: https://tools.ietf.org/html/rfc6455#section-10.2

2.0
...

* Backwards-incompatible API change:
  :meth:`~websockets.protocol.WebSocketCommonProtocol.send`,
  :meth:`~websockets.protocol.WebSocketCommonProtocol.ping` and
  :meth:`~websockets.protocol.WebSocketCommonProtocol.pong` are coroutines.
  They used to be regular functions.

* Added flow control.

1.0
...

* Initial public release.

Limitations
-----------

Extensions_ aren't implemented. No extensions are registered_ at the time of
writing.

The client doesn't attempt to guarantee that there is no more than one
connection to a given IP adress in a CONNECTING state.

The client doesn't support connecting through a proxy.

.. _Extensions: http://tools.ietf.org/html/rfc6455#section-9
.. _registered: http://www.iana.org/assignments/websocket/websocket.xml

License
-------

.. literalinclude:: ../LICENSE
