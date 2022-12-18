Both sides
==========

.. currentmodule:: websockets

What does ``ConnectionClosedError: no close frame received or sent`` mean?
--------------------------------------------------------------------------

If you're seeing this traceback in the logs of a server:

.. code-block:: pytb

    connection handler failed
    Traceback (most recent call last):
      ...
    asyncio.exceptions.IncompleteReadError: 0 bytes read on a total of 2 expected bytes

    The above exception was the direct cause of the following exception:

    Traceback (most recent call last):
      ...
    websockets.exceptions.ConnectionClosedError: no close frame received or sent

or if a client crashes with this traceback:

.. code-block:: pytb

    Traceback (most recent call last):
      ...
    ConnectionResetError: [Errno 54] Connection reset by peer

    The above exception was the direct cause of the following exception:

    Traceback (most recent call last):
      ...
    websockets.exceptions.ConnectionClosedError: no close frame received or sent

it means that the TCP connection was lost. As a consequence, the WebSocket
connection was closed without receiving and sending a close frame, which is
abnormal.

You can catch and handle :exc:`~exceptions.ConnectionClosed` to prevent it
from being logged.

There are several reasons why long-lived connections may be lost:

* End-user devices tend to lose network connectivity often and unpredictably
  because they can move out of wireless network coverage, get unplugged from
  a wired network, enter airplane mode, be put to sleep, etc.
* HTTP load balancers or proxies that aren't configured for long-lived
  connections may terminate connections after a short amount of time, usually
  30 seconds, despite websockets' keepalive mechanism.

If you're facing a reproducible issue, :ref:`enable debug logs <debugging>` to
see when and how connections are closed.

What does ``ConnectionClosedError: sent 1011 (unexpected error) keepalive ping timeout; no close frame received`` mean?
-----------------------------------------------------------------------------------------------------------------------

If you're seeing this traceback in the logs of a server:

.. code-block:: pytb

    connection handler failed
    Traceback (most recent call last):
      ...
    asyncio.exceptions.CancelledError

    The above exception was the direct cause of the following exception:

    Traceback (most recent call last):
      ...
    websockets.exceptions.ConnectionClosedError: sent 1011 (unexpected error) keepalive ping timeout; no close frame received

or if a client crashes with this traceback:

.. code-block:: pytb

    Traceback (most recent call last):
      ...
    asyncio.exceptions.CancelledError

    The above exception was the direct cause of the following exception:

    Traceback (most recent call last):
      ...
    websockets.exceptions.ConnectionClosedError: sent 1011 (unexpected error) keepalive ping timeout; no close frame received

it means that the WebSocket connection suffered from excessive latency and was
closed after reaching the timeout of websockets' keepalive mechanism.

You can catch and handle :exc:`~exceptions.ConnectionClosed` to prevent it
from being logged.

There are two main reasons why latency may increase:

* Poor network connectivity.
* More traffic than the recipient can handle.

See the discussion of :doc:`timeouts <../topics/timeouts>` for details.

If websockets' default timeout of 20 seconds is too short for your use case,
you can adjust it with the ``ping_timeout`` argument.

How do I set a timeout on :meth:`~legacy.protocol.WebSocketCommonProtocol.recv`?
--------------------------------------------------------------------------------

Use :func:`~asyncio.wait_for`::

    await asyncio.wait_for(websocket.recv(), timeout=10)

This technique works for most APIs, except for asynchronous context managers.
See `issue 574`_.

.. _issue 574: https://github.com/aaugustin/websockets/issues/574

How can I pass arguments to a custom protocol subclass?
-------------------------------------------------------

You can bind additional arguments to the protocol factory with
:func:`functools.partial`::

    import asyncio
    import functools
    import websockets

    class MyServerProtocol(websockets.WebSocketServerProtocol):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            # do something with kwargs['extra_argument']

    create_protocol = functools.partial(MyServerProtocol, extra_argument='spam')
    start_server = websockets.serve(..., create_protocol=create_protocol)

This example was for a server. The same pattern applies on a client.

How do I keep idle connections open?
------------------------------------

websockets sends pings at 20 seconds intervals to keep the connection open.

It closes the connection if it doesn't get a pong within 20 seconds.

You can adjust this behavior with ``ping_interval`` and ``ping_timeout``.

See :doc:`../topics/timeouts` for details.

How do I respond to pings?
--------------------------

Don't bother; websockets takes care of responding to pings with pongs.
