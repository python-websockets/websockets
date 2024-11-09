Both sides
==========

.. currentmodule:: websockets.asyncio.connection

What does ``ConnectionClosedError: no close frame received or sent`` mean?
--------------------------------------------------------------------------

If you're seeing this traceback in the logs of a server:

.. code-block:: pytb

    connection handler failed
    Traceback (most recent call last):
      ...
    websockets.exceptions.ConnectionClosedError: no close frame received or sent

or if a client crashes with this traceback:

.. code-block:: pytb

    Traceback (most recent call last):
      ...
    websockets.exceptions.ConnectionClosedError: no close frame received or sent

it means that the TCP connection was lost. As a consequence, the WebSocket
connection was closed without receiving and sending a close frame, which is
abnormal.

You can catch and handle :exc:`~websockets.exceptions.ConnectionClosed` to
prevent it from being logged.

There are several reasons why long-lived connections may be lost:

* End-user devices tend to lose network connectivity often and unpredictably
  because they can move out of wireless network coverage, get unplugged from
  a wired network, enter airplane mode, be put to sleep, etc.
* HTTP load balancers or proxies that aren't configured for long-lived
  connections may terminate connections after a short amount of time, usually
  30 seconds, despite websockets' keepalive mechanism.

If you're facing a reproducible issue, :ref:`enable debug logs <debugging>` to
see when and how connections are closed.

What does ``ConnectionClosedError: sent 1011 (internal error) keepalive ping timeout; no close frame received`` mean?
---------------------------------------------------------------------------------------------------------------------

If you're seeing this traceback in the logs of a server:

.. code-block:: pytb

    connection handler failed
    Traceback (most recent call last):
      ...
    websockets.exceptions.ConnectionClosedError: sent 1011 (internal error) keepalive ping timeout; no close frame received

or if a client crashes with this traceback:

.. code-block:: pytb

    Traceback (most recent call last):
      ...
    websockets.exceptions.ConnectionClosedError: sent 1011 (internal error) keepalive ping timeout; no close frame received

it means that the WebSocket connection suffered from excessive latency and was
closed after reaching the timeout of websockets' keepalive mechanism.

You can catch and handle :exc:`~websockets.exceptions.ConnectionClosed` to
prevent it from being logged.

There are two main reasons why latency may increase:

* Poor network connectivity.
* More traffic than the recipient can handle.

See the discussion of :doc:`keepalive <../topics/keepalive>` for details.

If websockets' default timeout of 20 seconds is too short for your use case,
you can adjust it with the ``ping_timeout`` argument.

How do I set a timeout on :meth:`~Connection.recv`?
---------------------------------------------------

On Python ≥ 3.11, use :func:`asyncio.timeout`::

    async with asyncio.timeout(timeout=10):
        message = await websocket.recv()

On older versions of Python, use :func:`asyncio.wait_for`::

    message = await asyncio.wait_for(websocket.recv(), timeout=10)

This technique works for most APIs. When it doesn't, for example with
asynchronous context managers, websockets provides an ``open_timeout`` argument.

How can I pass arguments to a custom connection subclass?
---------------------------------------------------------

You can bind additional arguments to the connection factory with
:func:`functools.partial`::

    import asyncio
    import functools
    from websockets.asyncio.server import ServerConnection, serve

    class MyServerConnection(ServerConnection):
        def __init__(self, *args, extra_argument=None, **kwargs):
            super().__init__(*args, **kwargs)
            # do something with extra_argument

    create_connection = functools.partial(ServerConnection, extra_argument=42)
    async with serve(..., create_connection=create_connection):
        ...

This example was for a server. The same pattern applies on a client.

How do I keep idle connections open?
------------------------------------

websockets sends pings at 20 seconds intervals to keep the connection open.

It closes the connection if it doesn't get a pong within 20 seconds.

You can adjust this behavior with ``ping_interval`` and ``ping_timeout``.

See :doc:`../topics/keepalive` for details.

How do I respond to pings?
--------------------------

If you are referring to Ping_ and Pong_ frames defined in the WebSocket
protocol, don't bother, because websockets handles them for you.

.. _Ping: https://datatracker.ietf.org/doc/html/rfc6455.html#section-5.5.2
.. _Pong: https://datatracker.ietf.org/doc/html/rfc6455.html#section-5.5.3

If you are connecting to a server that defines its own heartbeat at the
application level, then you need to build that logic into your application.
