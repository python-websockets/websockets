Cheat sheet
===========

Server
------

* Write a coroutine that handles a single connection. It receives a websocket
  protocol instance and the URI path in argument.

  * Call :meth:`~websockets.protocol.WebSocketCommonProtocol.recv` and
    :meth:`~websockets.protocol.WebSocketCommonProtocol.send` to receive and
    send messages at any time.

  * You may :meth:`~websockets.protocol.WebSocketCommonProtocol.ping` or
    :meth:`~websockets.protocol.WebSocketCommonProtocol.pong` if you wish
    but it isn't needed in general.

* Create a server with :func:`~websockets.server.serve` which is similar to
  asyncio's :meth:`~asyncio.AbstractEventLoop.create_server`.

  * The server takes care of establishing connections, then lets the handler
    execute the application logic, and finally closes the connection after
    the handler exits normally or with an exception.

  * For :ref:`advanced customization <custom-handling>`, you may subclass
    :class:`~websockets.server.WebSocketServerProtocol` and pass either this
    subclass or a factory function as the ``create_protocol`` argument.

Client
------

* Create a client with :func:`~websockets.client.connect` which is similar to
  asyncio's :meth:`~asyncio.BaseEventLoop.create_connection`.

  * On Python ≥ 3.5, you can also use it as an asynchronous context manager.

  * For advanced customization, you may subclass
    :class:`~websockets.server.WebSocketClientProtocol` and pass either this
    subclass or a factory function as the ``create_protocol`` argument.

* Call :meth:`~websockets.protocol.WebSocketCommonProtocol.recv` and
  :meth:`~websockets.protocol.WebSocketCommonProtocol.send` to receive and
  send messages at any time.

* You may :meth:`~websockets.protocol.WebSocketCommonProtocol.ping` or
  :meth:`~websockets.protocol.WebSocketCommonProtocol.pong` if you wish but it
  isn't needed in general.

* If you aren't using :func:`~websockets.client.connect` as a context manager,
  call :meth:`~websockets.protocol.WebSocketCommonProtocol.close` to terminate
  the connection.

Debugging
---------

If you don't understand what ``websockets`` is doing, enable logging::

    import logging
    logger = logging.getLogger('websockets')
    logger.setLevel(logging.INFO)
    logger.addHandler(logging.StreamHandler())

The logs contain:

* Exceptions in the connection handler at the ``ERROR`` level
* Exceptions in the opening or closing handshake at the ``INFO`` level
* All frames at the ``DEBUG`` level — this can be very verbose

If you're new to ``asyncio``, you will certainly encounter issues that are
related to asynchronous programming in general rather than to ``websockets``
in particular. Fortunately Python's official documentation provides advice to
`develop with asyncio`_. Check it out: it's invaluable!

.. _develop with asyncio: https://docs.python.org/3/library/asyncio-dev.html

Keeping connections open
------------------------

Pinging the other side once in a while is a good way to check whether the
connection is still working, and also to keep it open in case something kills
idle connections after some time::

    while True:
        try:
            msg = await asyncio.wait_for(ws.recv(), timeout=20)
        except asyncio.TimeoutError:
            # No data in 20 seconds, check the connection.
            try:
                await asyncio.wait_for(ws.ping(), timeout=10)
            except asyncio.TimeoutError:
                # No response to ping in 10 seconds, disconnect.
                break
        else:
            # do something with msg
            ...
