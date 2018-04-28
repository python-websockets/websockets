Cheat sheet
===========

.. currentmodule:: websockets

Server
------

* Write a coroutine that handles a single connection. It receives a websocket
  protocol instance and the URI path in argument.

  * Call :meth:`~protocol.WebSocketCommonProtocol.recv` and
    :meth:`~protocol.WebSocketCommonProtocol.send` to receive and send
    messages at any time.

  * You may :meth:`~protocol.WebSocketCommonProtocol.ping` or
    :meth:`~protocol.WebSocketCommonProtocol.pong` if you wish but it isn't
    needed in general.

* Create a server with :func:`~server.serve` which is similar to asyncio's
  :meth:`~asyncio.AbstractEventLoop.create_server`.

  * On Python ≥ 3.5.1, you can also use it as an asynchronous context manager.

  * The server takes care of establishing connections, then lets the handler
    execute the application logic, and finally closes the connection after the
    handler exits normally or with an exception.

  * For advanced customization, you may subclass
    :class:`~server.WebSocketServerProtocol` and pass either this subclass or
    a factory function as the ``create_protocol`` argument.

Client
------

* Create a client with :func:`~client.connect` which is similar to asyncio's
  :meth:`~asyncio.BaseEventLoop.create_connection`.

  * On Python ≥ 3.5.1, you can also use it as an asynchronous context manager.

  * For advanced customization, you may subclass
    :class:`~server.WebSocketClientProtocol` and pass either this subclass or
    a factory function as the ``create_protocol`` argument.

* Call :meth:`~protocol.WebSocketCommonProtocol.recv` and
  :meth:`~protocol.WebSocketCommonProtocol.send` to receive and send messages
  at any time.

* You may :meth:`~protocol.WebSocketCommonProtocol.ping` or
  :meth:`~protocol.WebSocketCommonProtocol.pong` if you wish but it isn't
  needed in general.

* If you aren't using :func:`~client.connect` as a context manager, call
  :meth:`~protocol.WebSocketCommonProtocol.close` to terminate the connection.

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
                pong_waiter = await ws.ping()
                await asyncio.wait_for(pong_waiter, timeout=10)
            except asyncio.TimeoutError:
                # No response to ping in 10 seconds, disconnect.
                break
        else:
            # do something with msg
            ...

Passing additional arguments to the connection handler
------------------------------------------------------

When writing a server, if you need to pass additional arguments to the
connection handler, you can bind them with :func:`functools.partial`::

    import asyncio
    import functools
    import websockets

    async def handler(websocket, path, extra_argument):
        ...

    bound_handler = functools.partial(handler, extra_argument='spam')
    start_server = websockets.serve(bound_handler, '127.0.0.1', 8765)

    asyncio.get_event_loop().run_until_complete(start_server)
    asyncio.get_event_loop().run_forever()

Another way to achieve this result is to define the ``handler`` corountine in
a scope where the ``extra_argument`` variable exists instead of injecting it
through an argument.
