Upgrade to the new :mod:`asyncio` implementation
================================================

.. currentmodule:: websockets

The new :mod:`asyncio` implementation, which is now the default, is a rewrite of
the original implementation of websockets.

It provides a very similar API. However, there are a few differences.

The recommended upgrade process is:

#. Make sure that your code doesn't use any `deprecated APIs`_. If it doesn't
   raise warnings, you're fine.
#. `Update import paths`_. For straightforward use cases, this could be the only
   step you need to take.
#. Check out `new features and improvements`_. Consider taking advantage of them
   in your code.
#. Review `API changes`_. If needed, update your application to preserve its
   current behavior.

In the interest of brevity, only :func:`~asyncio.client.connect` and
:func:`~asyncio.server.serve` are discussed below but everything also applies
to :func:`~asyncio.client.unix_connect` and :func:`~asyncio.server.unix_serve`
respectively.

.. admonition:: What will happen to the original implementation?
    :class: hint

    The original implementation is deprecated. It will be maintained for five
    years after deprecation according to the :ref:`backwards-compatibility
    policy <backwards-compatibility policy>`. Then, by 2030, it will be removed.

.. _deprecated APIs:

Deprecated APIs
---------------

Here's the list of deprecated behaviors that the original implementation still
supports and that the new implementation doesn't reproduce.

If you're seeing a :class:`DeprecationWarning`, follow upgrade instructions from
the release notes of the version in which the feature was deprecated.

* The ``path`` argument of connection handlers — unnecessary since :ref:`10.1`
  and deprecated in :ref:`13.0`.
* The ``loop`` and ``legacy_recv`` arguments of :func:`~legacy.client.connect`
  and :func:`~legacy.server.serve`, which were removed — deprecated in
  :ref:`10.0`.
* The ``timeout`` and ``klass`` arguments of :func:`~legacy.client.connect` and
  :func:`~legacy.server.serve`, which were renamed to ``close_timeout`` and
  ``create_protocol`` — deprecated in :ref:`7.0` and :ref:`3.4` respectively.
* An empty string in the ``origins`` argument of :func:`~legacy.server.serve` —
  deprecated in :ref:`7.0`.
* The ``host``, ``port``, and ``secure`` attributes of connections — deprecated
  in :ref:`8.0`.

.. _Update import paths:

Import paths
------------

For context, the ``websockets`` package is structured as follows:

* The new implementation is found in the ``websockets.asyncio`` package.
* The original implementation was moved to the ``websockets.legacy`` package
  and deprecated.
* The ``websockets`` package provides aliases for convenience. They were
  switched to the new implementation in version 14.0 or deprecated when there
  wasn't an equivalent API.
* The ``websockets.client`` and ``websockets.server`` packages provide aliases
  for backwards-compatibility with earlier versions of websockets. They were
  deprecated.

To upgrade to the new :mod:`asyncio` implementation, change import paths as
shown in the tables below.

.. |br| raw:: html

    <br/>

Client APIs
...........

+-------------------------------------------------------------------+-----------------------------------------------------+
| Legacy :mod:`asyncio` implementation                              | New :mod:`asyncio` implementation                   |
+===================================================================+=====================================================+
| ``websockets.connect()`` *(before 14.0)*                     |br| | ``websockets.connect()`` *(since 14.0)*        |br| |
| ``websockets.client.connect()``                              |br| | :func:`websockets.asyncio.client.connect`           |
| :func:`websockets.legacy.client.connect`                          |                                                     |
+-------------------------------------------------------------------+-----------------------------------------------------+
| ``websockets.unix_connect()`` *(before 14.0)*                |br| | ``websockets.unix_connect()`` *(since 14.0)*   |br| |
| ``websockets.client.unix_connect()``                         |br| | :func:`websockets.asyncio.client.unix_connect`      |
| :func:`websockets.legacy.client.unix_connect`                     |                                                     |
+-------------------------------------------------------------------+-----------------------------------------------------+
| ``websockets.WebSocketClientProtocol``                       |br| | ``websockets.ClientConnection`` *(since 14.2)* |br| |
| ``websockets.client.WebSocketClientProtocol``                |br| | :class:`websockets.asyncio.client.ClientConnection` |
| :class:`websockets.legacy.client.WebSocketClientProtocol`         |                                                     |
+-------------------------------------------------------------------+-----------------------------------------------------+

Server APIs
...........

+-------------------------------------------------------------------+-----------------------------------------------------+
| Legacy :mod:`asyncio` implementation                              | New :mod:`asyncio` implementation                   |
+===================================================================+=====================================================+
| ``websockets.serve()`` *(before 14.0)*                       |br| | ``websockets.serve()`` *(since 14.0)*          |br| |
| ``websockets.server.serve()``                                |br| | :func:`websockets.asyncio.server.serve`             |
| :func:`websockets.legacy.server.serve`                            |                                                     |
+-------------------------------------------------------------------+-----------------------------------------------------+
| ``websockets.unix_serve()`` *(before 14.0)*                  |br| | ``websockets.unix_serve()`` *(since 14.0)*     |br| |
| ``websockets.server.unix_serve()``                           |br| | :func:`websockets.asyncio.server.unix_serve`        |
| :func:`websockets.legacy.server.unix_serve`                       |                                                     |
+-------------------------------------------------------------------+-----------------------------------------------------+
| ``websockets.WebSocketServer``                               |br| | ``websockets.Server`` *(since 14.2)*           |br| |
| ``websockets.server.WebSocketServer``                        |br| | :class:`websockets.asyncio.server.Server`           |
| :class:`websockets.legacy.server.WebSocketServer`                 |                                                     |
+-------------------------------------------------------------------+-----------------------------------------------------+
| ``websockets.WebSocketServerProtocol``                       |br| | ``websockets.ServerConnection`` *(since 14.2)* |br| |
| ``websockets.server.WebSocketServerProtocol``                |br| | :class:`websockets.asyncio.server.ServerConnection` |
| :class:`websockets.legacy.server.WebSocketServerProtocol`         |                                                     |
+-------------------------------------------------------------------+-----------------------------------------------------+
| ``websockets.broadcast()`` *(before 14.0)*                   |br| | ``websockets.broadcast()`` *(since 14.0)*      |br| |
| :func:`websockets.legacy.server.broadcast()`                      | :func:`websockets.asyncio.server.broadcast`         |
+-------------------------------------------------------------------+-----------------------------------------------------+
| ``websockets.BasicAuthWebSocketServerProtocol``              |br| | See below :ref:`how to migrate <basic-auth>` to     |
| ``websockets.auth.BasicAuthWebSocketServerProtocol``         |br| | :func:`websockets.asyncio.server.basic_auth`.       |
| :class:`websockets.legacy.auth.BasicAuthWebSocketServerProtocol`  |                                                     |
+-------------------------------------------------------------------+-----------------------------------------------------+
| ``websockets.basic_auth_protocol_factory()``                 |br| | See below :ref:`how to migrate <basic-auth>` to     |
| ``websockets.auth.basic_auth_protocol_factory()``            |br| | :func:`websockets.asyncio.server.basic_auth`.       |
| :func:`websockets.legacy.auth.basic_auth_protocol_factory`        |                                                     |
+-------------------------------------------------------------------+-----------------------------------------------------+

.. _new features and improvements:

New features and improvements
-----------------------------

Customizing the opening handshake
.................................

On the server side, if you're customizing how :func:`~legacy.server.serve`
processes the opening handshake with ``process_request``, ``extra_headers``, or
``select_subprotocol``, you must update your code. Probably you can simplify it!

``process_request`` and ``select_subprotocol`` have new signatures.
``process_response`` replaces ``extra_headers`` and provides more flexibility.
See process_request_, select_subprotocol_, and process_response_ below.

Customizing automatic reconnection
..................................

On the client side, if you're reconnecting automatically with ``async for ... in
connect(...)``, the behavior when a connection attempt fails was enhanced and
made configurable.

The original implementation retried on any error. The new implementation uses an
heuristic to determine whether an error is retryable or fatal. By default, only
network errors and server errors (HTTP 500, 502, 503, or 504) are considered
retryable. You can customize this behavior with the ``process_exception``
argument of :func:`~asyncio.client.connect`.

See :func:`~asyncio.client.process_exception` for more information.

Here's how to revert to the behavior of the original implementation::

    async for ... in connect(..., process_exception=lambda exc: exc):
        ...

Tracking open connections
.........................

The new implementation of :class:`~asyncio.server.Server` provides a
:attr:`~asyncio.server.Server.connections` property, which is a set of all open
connections. This didn't exist in the original implementation.

If you're keeping track of open connections in order to broadcast messages to
all of them, you can simplify your code by using this property.

Controlling UTF-8 decoding
..........................

The new implementation of the :meth:`~asyncio.connection.Connection.recv` method
provides the ``decode`` argument to control UTF-8 decoding of messages. This
didn't exist in the original implementation.

If you're calling :meth:`~str.encode` on a :class:`str` object returned by
:meth:`~asyncio.connection.Connection.recv`, using ``decode=False`` and removing
:meth:`~str.encode` saves a round-trip of UTF-8 decoding and encoding for text
messages.

You can also force UTF-8 decoding of binary messages with ``decode=True``. This
is rarely useful and has no performance benefits over decoding a :class:`bytes`
object returned by :meth:`~asyncio.connection.Connection.recv`.

Receiving fragmented messages
.............................

The new implementation provides the
:meth:`~asyncio.connection.Connection.recv_streaming` method for receiving a
fragmented message frame by frame. There was no way to do this in the original
implementation.

Depending on your use case, adopting this method may improve performance when
streaming large messages. Specifically, it could reduce memory usage.

.. _API changes:

API changes
-----------

Attributes of connection objects
................................

``path``, ``request_headers``, and ``response_headers``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The :attr:`~legacy.protocol.WebSocketCommonProtocol.path`,
:attr:`~legacy.protocol.WebSocketCommonProtocol.request_headers` and
:attr:`~legacy.protocol.WebSocketCommonProtocol.response_headers` properties are
replaced by :attr:`~asyncio.connection.Connection.request` and
:attr:`~asyncio.connection.Connection.response`.

If your code uses them, you can update it as follows.

==========================================  ==========================================
Legacy :mod:`asyncio` implementation        New :mod:`asyncio` implementation
==========================================  ==========================================
``connection.path``                         ``connection.request.path``
``connection.request_headers``              ``connection.request.headers``
``connection.response_headers``             ``connection.response.headers``
==========================================  ==========================================

``open`` and ``closed``
~~~~~~~~~~~~~~~~~~~~~~~

The :attr:`~legacy.protocol.WebSocketCommonProtocol.open` and
:attr:`~legacy.protocol.WebSocketCommonProtocol.closed` properties are removed.
Using them was discouraged.

Instead, you should call :meth:`~asyncio.connection.Connection.recv` or
:meth:`~asyncio.connection.Connection.send` and handle
:exc:`~exceptions.ConnectionClosed` exceptions.

If your code uses them, you can update it as follows.

==========================================  ==========================================
Legacy :mod:`asyncio` implementation        New :mod:`asyncio` implementation
==========================================  ==========================================
..                                          ``from websockets.protocol import State``
``connection.open``                         ``connection.state is State.OPEN``
``connection.closed``                       ``connection.state is State.CLOSED``
==========================================  ==========================================

Arguments of :func:`~asyncio.client.connect`
............................................

``extra_headers`` → ``additional_headers``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If you're adding headers to the handshake request sent by
:func:`~legacy.client.connect` with the ``extra_headers`` argument, you must
rename it to ``additional_headers``.

Arguments of :func:`~asyncio.server.serve`
..........................................

``ws_handler`` → ``handler``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The first argument of :func:`~asyncio.server.serve` is now called ``handler``
instead of ``ws_handler``. It's usually passed as a positional argument, making
this change transparent. If you're passing it as a keyword argument, you must
update its name.

.. _process_request:

``process_request``
~~~~~~~~~~~~~~~~~~~

The signature of ``process_request`` changed. This is easiest to illustrate with
an example::

    import http

    # Original implementation

    def process_request(path, request_headers):
        return http.HTTPStatus.OK, [], b"OK\n"

    # New implementation

    def process_request(connection, request):
        return connection.respond(http.HTTPStatus.OK, "OK\n")

    serve(..., process_request=process_request, ...)

``connection`` is always available in ``process_request``. In the original
implementation, if you wanted to make the connection object available in a
``process_request`` method, you had to write a subclass of
:class:`~legacy.server.WebSocketServerProtocol` and pass it in the
``create_protocol`` argument. This pattern isn't useful anymore; you can
replace it with a ``process_request`` function or coroutine.

``path`` and ``headers`` are available as attributes of the ``request`` object.

.. _process_response:

``extra_headers`` → ``process_response``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If you're adding headers to the handshake response sent by
:func:`~legacy.server.serve` with the ``extra_headers`` argument, you must write
a ``process_response`` callable instead.

``process_request`` replaces ``extra_headers`` and provides more flexibility.
In the most basic case, you would adapt your code as follows::

    # Original implementation

    serve(..., extra_headers=HEADERS, ...)

    # New implementation

    def process_response(connection, request, response):
        response.headers.update(HEADERS)
        return response

    serve(..., process_response=process_response, ...)

``connection`` is always available in ``process_response``, similar to
``process_request``. In the original implementation, there was no way to make
the connection object available.

In addition, the ``request`` and ``response`` objects are available, which
enables a broader range of use cases (e.g., logging) and makes
``process_response`` more useful than ``extra_headers``.

.. _select_subprotocol:

``select_subprotocol``
~~~~~~~~~~~~~~~~~~~~~~

If you're selecting a subprotocol, you must update your code because the
signature of ``select_subprotocol`` changed. Here's an example::

    # Original implementation

    def select_subprotocol(client_subprotocols, server_subprotocols):
        if "chat" in client_subprotocols:
            return "chat"

    # New implementation

    def select_subprotocol(connection, subprotocols):
        if "chat" in subprotocols
            return "chat"

    serve(..., select_subprotocol=select_subprotocol, ...)

``connection`` is always available in ``select_subprotocol``. This brings the
same benefits as in ``process_request``. It may remove the need to subclass
:class:`~legacy.server.WebSocketServerProtocol`.

The ``subprotocols`` argument contains the list of subprotocols offered by the
client. The list of subprotocols supported by the server was removed because
``select_subprotocols`` has to know which subprotocols it may select and under
which conditions.

Furthermore, the default behavior when ``select_subprotocol`` isn't provided
changed in two ways:

1. In the original implementation, a server with a list of subprotocols accepted
   to continue without a subprotocol. In the new implementation, a server that
   is configured with subprotocols rejects connections that don't support any.
2. In the original implementation, when several subprotocols were available, the
   server averaged the client's preferences with its own preferences. In the new
   implementation, the server just picks the first subprotocol from its list.

If you had a ``select_subprotocol`` for the sole purpose of rejecting
connections without a subprotocol, you can remove it and keep only the
``subprotocols`` argument.

Arguments of :func:`~asyncio.client.connect` and :func:`~asyncio.server.serve`
..............................................................................

``max_queue``
~~~~~~~~~~~~~

The ``max_queue`` argument of :func:`~asyncio.client.connect` and
:func:`~asyncio.server.serve` has a new meaning but achieves a similar effect.

It is now the high-water mark of a buffer of incoming frames. It defaults to 16
frames. It used to be the size of a buffer of incoming messages that refilled as
soon as a message was read. It used to default to 32 messages.

This can make a difference when messages are fragmented in several frames. In
that case, you may want to increase ``max_queue``.

If you're writing a high performance server and you know that you're receiving
fragmented messages, probably you should adopt
:meth:`~asyncio.connection.Connection.recv_streaming` and optimize the
performance of reads again.

In all other cases, given how uncommon fragmentation is, you shouldn't worry
about this change.

``read_limit``
~~~~~~~~~~~~~~

The ``read_limit`` argument doesn't exist in the new implementation because it
doesn't buffer data received from the network in a
:class:`~asyncio.StreamReader`. With a better design, this buffer could be
removed.

The buffer of incoming frames configured by ``max_queue`` is the only read
buffer now.

``write_limit``
~~~~~~~~~~~~~~~

The ``write_limit`` argument of :func:`~asyncio.client.connect` and
:func:`~asyncio.server.serve` defaults to 32 KiB instead of 64 KiB.

``create_protocol`` → ``create_connection``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The keyword argument of :func:`~asyncio.server.serve` for customizing the
creation of the connection object is now called ``create_connection`` instead of
``create_protocol``. It must return a :class:`~asyncio.server.ServerConnection`
instead of a :class:`~legacy.server.WebSocketServerProtocol`.

If you were customizing connection objects, probably you need to redo your
customization. Consider switching to ``process_request`` and
``select_subprotocol`` as their new design removes most use cases for
``create_connection``.

.. _basic-auth:

Performing HTTP Basic Authentication
....................................

.. admonition:: This section applies only to servers.
    :class: tip

    On the client side, :func:`~asyncio.client.connect` performs HTTP Basic
    Authentication automatically when the URI contains credentials.

In the original implementation, the recommended way to add HTTP Basic
Authentication to a server was to set the ``create_protocol`` argument of
:func:`~legacy.server.serve` to a factory function generated by
:func:`~legacy.auth.basic_auth_protocol_factory`::

    from websockets.legacy.auth import basic_auth_protocol_factory
    from websockets.legacy.server import serve

    async with serve(..., create_protocol=basic_auth_protocol_factory(...)):
        ...

In the new implementation, the :func:`~asyncio.server.basic_auth` function
generates a ``process_request`` coroutine that performs HTTP Basic
Authentication::

    from websockets.asyncio.server import basic_auth, serve

    async with serve(..., process_request=basic_auth(...)):
        ...

:func:`~asyncio.server.basic_auth` accepts either hard coded ``credentials`` or
a ``check_credentials`` coroutine as well as an optional ``realm`` just like
:func:`~legacy.auth.basic_auth_protocol_factory`. Furthermore,
``check_credentials`` may be a function instead of a coroutine.

This new API has more obvious semantics. That makes it easier to understand and
also easier to extend.

In the original implementation, overriding ``create_protocol`` changes the type
of connection objects to :class:`~legacy.auth.BasicAuthWebSocketServerProtocol`,
a subclass of :class:`~legacy.server.WebSocketServerProtocol` that performs HTTP
Basic Authentication in its ``process_request`` method.

To customize ``process_request`` further, you had only bad options:

* the ill-defined option: add a ``process_request`` argument to
  :func:`~legacy.server.serve`; to tell which one would run first, you had to
  experiment or read the code;
* the cumbersome option: subclass
  :class:`~legacy.auth.BasicAuthWebSocketServerProtocol`, then pass that
  subclass in the ``create_protocol`` argument of
  :func:`~legacy.auth.basic_auth_protocol_factory`.

In the new implementation, you just write a ``process_request`` coroutine::

    from websockets.asyncio.server import basic_auth, serve

    process_basic_auth = basic_auth(...)

    async def process_request(connection, request):
        ...  # some logic here
        response = await process_basic_auth(connection, request)
        if response is not None:
            return response
        ... # more logic here

    async with serve(..., process_request=process_request):
        ...
