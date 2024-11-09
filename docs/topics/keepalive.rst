Keepalive and latency
=====================

.. admonition:: This guide applies only to the :mod:`asyncio` implementation.
    :class: tip

    The :mod:`threading` implementation doesn't provide keepalive yet.

.. currentmodule:: websockets

Long-lived connections
----------------------

Since the WebSocket protocol is intended for real-time communications over
long-lived connections, it is desirable to ensure that connections don't
break, and if they do, to report the problem quickly.

Connections can drop as a consequence of temporary network connectivity issues,
which are very common, even within data centers.

Furthermore, WebSocket builds on top of HTTP/1.1 where connections are
short-lived, even with ``Connection: keep-alive``. Typically, HTTP/1.1
infrastructure closes idle connections after 30 to 120 seconds.

As a consequence, proxies may terminate WebSocket connections prematurely when
no message was exchanged in 30 seconds.

.. _keepalive:

Keepalive in websockets
-----------------------

To avoid these problems, websockets runs a keepalive and heartbeat mechanism
based on WebSocket Ping_ and Pong_ frames, which are designed for this purpose.

.. _Ping: https://datatracker.ietf.org/doc/html/rfc6455.html#section-5.5.2
.. _Pong: https://datatracker.ietf.org/doc/html/rfc6455.html#section-5.5.3

It sends a Ping frame every 20 seconds. It expects a Pong frame in return within
20 seconds. Else, it considers the connection broken and terminates it.

This mechanism serves three purposes:

1. It creates a trickle of traffic so that the TCP connection isn't idle and
   network infrastructure along the path keeps it open ("keepalive").
2. It detects if the connection drops or becomes so slow that it's unusable in
   practice ("heartbeat"). In that case, it terminates the connection and your
   application gets a :exc:`~exceptions.ConnectionClosed` exception.
3. It measures the :attr:`~asyncio.connection.Connection.latency` of the
   connection. The time between sending a Ping frame and receiving a matching
   Pong frame approximates the round-trip time.

Timings are configurable with the ``ping_interval`` and ``ping_timeout``
arguments of :func:`~asyncio.client.connect` and :func:`~asyncio.server.serve`.
Shorter values will detect connection drops faster but they will increase
network traffic and they will be more sensitive to latency.

Setting ``ping_interval`` to :obj:`None` disables the whole keepalive and
heartbeat mechanism, including measurement of latency.

Setting ``ping_timeout`` to :obj:`None` disables only timeouts. This enables
keepalive, to keep idle connections open, and disables heartbeat, to support large
latency spikes.

.. admonition:: Why doesn't websockets rely on TCP keepalive?
    :class: hint

    TCP keepalive is disabled by default on most operating systems. When
    enabled, the default interval is two hours or more, which is far too much.

Keepalive in browsers
---------------------

Browsers don't enable a keepalive mechanism like websockets by default. As a
consequence, they can fail to notice that a WebSocket connection is broken for
an extended period of time, until the TCP connection times out.

In this scenario, the ``WebSocket`` object in the browser doesn't fire a
``close`` event. If you have a reconnection mechanism, it doesn't kick in
because it believes that the connection is still working.

If your browser-based app mysteriously and randomly fails to receive events,
this is a likely cause. You need a keepalive mechanism in the browser to avoid
this scenario.

Unfortunately, the WebSocket API in browsers doesn't expose the native Ping and
Pong functionality in the WebSocket protocol. You have to roll your own in the
application layer.

Read this `blog post <https://making.close.com/posts/reliable-websockets/>`_ for
a complete walk-through of this issue.

Application-level keepalive
---------------------------

Some servers require clients to send a keepalive message with a specific content
at regular intervals. Usually they expect Text_ frames rather than Ping_ frames,
meaning that you must send them with :attr:`~asyncio.connection.Connection.send`
rather than :attr:`~asyncio.connection.Connection.ping`.

.. _Text: https://datatracker.ietf.org/doc/html/rfc6455.html#section-5.6

In websockets, such keepalive mechanisms are considered as application-level
because they rely on data frames. That's unlike the protocol-level keepalive
based on control frames. Therefore, it's your responsibility to implement the
required behavior.

You can run a task in the background to send keepalive messages:

.. code-block:: python

    import itertools
    import json

    from websockets.exceptions import ConnectionClosed

    async def keepalive(websocket, ping_interval=30):
        for ping in itertools.count():
            await asyncio.sleep(ping_interval)
            try:
                await websocket.send(json.dumps({"ping": ping}))
            except ConnectionClosed:
                break

    async def main():
        async with connect(...) as websocket:
            keepalive_task = asyncio.create_task(keepalive(websocket))
            try:
                ... # your application logic goes here
            finally:
                keepalive_task.cancel()

Latency issues
--------------

The :attr:`~asyncio.connection.Connection.latency` attribute stores latency
measured during the last exchange of Ping and Pong frames::

    latency = websocket.latency

Alternatively, you can measure the latency at any time by calling
:attr:`~asyncio.connection.Connection.ping` and awaiting its result::

    pong_waiter = await websocket.ping()
    latency = await pong_waiter

Latency between a client and a server may increase for two reasons:

* Network connectivity is poor. When network packets are lost, TCP attempts to
  retransmit them, which manifests as latency. Excessive packet loss makes
  the connection unusable in practice. At some point, timing out is a
  reasonable choice.

* Traffic is high. For example, if a client sends messages on the connection
  faster than a server can process them, this manifests as latency as well,
  because data is waiting in :doc:`buffers <memory>`.

  If the server is more than 20 seconds behind, it doesn't see the Pong before
  the default timeout elapses. As a consequence, it closes the connection.
  This is a reasonable choice to prevent overload.

  If traffic spikes cause unwanted timeouts and you're confident that the server
  will catch up eventually, you can increase ``ping_timeout`` or you can set it
  to :obj:`None` to disable heartbeat entirely.

  The same reasoning applies to situations where the server sends more traffic
  than the client can accept.
