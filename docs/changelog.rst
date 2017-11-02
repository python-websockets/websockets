Changelog
---------

.. currentmodule:: websockets

4.1
...

*In development*

4.0
...

.. warning::

    **Version 4.0 enables compression with the permessage-deflate extension.**

    In August 2017, Firefox and Chrome support it, but not Safari and IE.

    Compression should improve performance but it increases RAM and CPU use.

    If you want to disable compression, add ``compression=None`` when calling
    :func:`~server.serve()` or :func:`~client.connect()`.

.. warning::

    **Version 4.0 removes the ``state_name`` attribute of protocols.**

    Use ``protocol.state.name`` instead of ``protocol.state_name``.

Also:

* :class:`~protocol.WebSocketCommonProtocol` instances can be used as
  asynchronous iterators on Python ≥ 3.6. They yield incoming messages.

* Added :func:`~websockets.server.unix_serve` for listening on Unix sockets.

* Added the :attr:`~websockets.server.WebSocketServer.sockets` attribute.

* Reorganized and extended documentation.

* Aborted connections if they don't close within the configured ``timeout``.

* Rewrote connection termination to increase robustness in edge cases.

* Stopped leaking pending tasks when :meth:`~asyncio.Task.cancel` is called on
  a connection while it's being closed.

* Reduced verbosity of "Failing the WebSocket connection" logs.

* Allowed ``extra_headers`` to override ``Server`` and ``User-Agent`` headers.

3.4
...

* Renamed :func:`~server.serve()` and :func:`~client.connect()`'s ``klass``
  argument to ``create_protocol`` to reflect that it can also be a callable.
  For backwards compatibility, ``klass`` is still supported.

* :func:`~server.serve` can be used as an asynchronous context manager on
  Python ≥ 3.5.

* Added support for customizing handling of incoming connections with
  :meth:`~server.WebSocketServerProtocol.process_request()`.

* Made read and write buffer sizes configurable.

* Rewrote HTTP handling for simplicity and performance.

* Added an optional C extension to speed up low level operations.

* An invalid response status code during :func:`~client.connect()` now raises
  :class:`~exceptions.InvalidStatusCode` with a ``code`` attribute.

* Providing a ``sock`` argument to :func:`~client.connect()` no longer
  crashes.

3.3
...

* Reduced noise in logs caused by connection resets.

* Avoided crashing on concurrent writes on slow connections.

3.2
...

* Added ``timeout``, ``max_size``, and ``max_queue`` arguments to
  :func:`~client.connect()` and :func:`~server.serve()`.

* Made server shutdown more robust.

3.1
...

* Avoided a warning when closing a connection before the opening handshake.

* Added flow control for incoming data.

3.0
...

.. warning::

    **Version 3.0 introduces a backwards-incompatible change in the**
    :meth:`~protocol.WebSocketCommonProtocol.recv` **API.**

    **If you're upgrading from 2.x or earlier, please read this carefully.**

    :meth:`~protocol.WebSocketCommonProtocol.recv` used to return ``None``
    when the connection was closed. This required checking the return value of
    every call::

        message = await websocket.recv()
        if message is None:
            return

    Now it raises a :exc:`~exceptions.ConnectionClosed` exception instead.
    This is more Pythonic. The previous code can be simplified to::

        message = await websocket.recv()

    When implementing a server, which is the more popular use case, there's no
    strong reason to handle such exceptions. Let them bubble up, terminate the
    handler coroutine, and the server will simply ignore them.

    In order to avoid stranding projects built upon an earlier version, the
    previous behavior can be restored by passing ``legacy_recv=True`` to
    :func:`~server.serve`, :func:`~client.connect`,
    :class:`~server.WebSocketServerProtocol`, or
    :class:`~client.WebSocketClientProtocol`. ``legacy_recv`` isn't documented
    in their signatures but isn't scheduled for deprecation either.

Also:

* :func:`~client.connect` can be used as an asynchronous context manager on
  Python ≥ 3.5.

* Updated documentation with ``await`` and ``async`` syntax from Python 3.5.

* :meth:`~protocol.WebSocketCommonProtocol.ping` and
  :meth:`~protocol.WebSocketCommonProtocol.pong` support data passed as
  :class:`str` in addition to :class:`bytes`.

* Worked around an asyncio bug affecting connection termination under load.

* Made ``state_name`` atttribute on protocols a public API.

* Improved documentation.

2.7
...

* Added compatibility with Python 3.5.

* Refreshed documentation.

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

* Returned a 403 status code instead of 400 when the request Origin isn't
  allowed.

* Cancelling :meth:`~protocol.WebSocketCommonProtocol.recv` no longer drops
  the next message.

* Clarified that the closing handshake can be initiated by the client.

* Set the close code and reason more consistently.

* Strengthened connection termination by simplifying the implementation.

* Improved tests, added tox configuration, and enforced 100% branch coverage.

2.4
...

* Added support for subprotocols.

* Supported non-default event loop.

* Added ``loop`` argument to :func:`~client.connect` and
  :func:`~server.serve`.

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

.. warning::

    **Version 2.0 introduces a backwards-incompatible change in the**
    :meth:`~protocol.WebSocketCommonProtocol.send`,
    :meth:`~protocol.WebSocketCommonProtocol.ping`, and
    :meth:`~protocol.WebSocketCommonProtocol.pong` **APIs.**

    **If you're upgrading from 1.x or earlier, please read this carefully.**

    These APIs used to be functions. Now they're coroutines.

    Instead of::

        websocket.send(message)

    you must now write::

        await websocket.send(message)

Also:

* Added flow control for outgoing data.

1.0
...

* Initial public release.
