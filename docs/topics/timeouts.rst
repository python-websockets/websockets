Timeouts
========

Since the WebSocket protocol is intended for real-time communications over
long-lived connections, it is desirable to ensure that connections don't
break, and if they do, to report the problem quickly.

WebSocket is built on top of HTTP/1.1 where connections are short-lived, even
with ``Connection: keep-alive``. Typically, HTTP/1.1 infrastructure closes
idle connections after 30 to 120 seconds.

As a consequence, proxies may terminate WebSocket connections prematurely,
when no message was exchanged in 30 seconds.

In order to avoid this problem, websockets implements a keepalive mechanism
based on WebSocket Ping and Pong frames. Ping and Pong are designed for this
purpose.

By default, websockets waits 20 seconds, then sends a Ping frame, and expects
to receive the corresponding Pong frame within 20 seconds. Else, it considers
the connection broken and closes it.

Timings are configurable with ``ping_interval`` and ``ping_timeout``.

While WebSocket runs on top of TCP, websockets doesn't rely on TCP keepalive
because it's disabled by default and, if enabled, the default interval is no
less than two hours, which doesn't meet requirements.

Latency between a client and a server may increase for two reasons:

* Network connectivity is poor. When network packets are lost, TCP attempts to
  retransmit them, which manifests as latency. Excessive packet loss makes
  the connection unusable in practice. At some point, timing out is a
  reasonable choice.

* Traffic is high. For example, if a client sends messages on the connection
  faster than a server can process them, this manifests as latency as well,
  because data is waiting in flight, mostly in OS buffers.

  If the server is more than 20 seconds behind, it doesn't see the Pong before
  the default timeout elapses. As a consequence, it closes the connection.
  This is a reasonable choice to prevent overload.

  If traffic spikes cause unwanted timeouts and you're confident that the
  server will catch up eventually, you can increase ``ping_timeout`` or you
  can disable keepalive entirely with ``ping_interval=None``.

  The same reasoning applies to situations where the server sends more traffic
  than the client can accept.

You can monitor latency as follows:

.. code:: python

    import asyncio
    import logging
    import time

    async def log_latency(websocket, logger):
        t0 = time.perf_counter()
        pong_waiter = await websocket.ping()
        await pong_waiter
        t1 = time.perf_counter()
        logger.info("Connection latency: %.3f seconds", t1 - t0)

    asyncio.create_task(log_latency(websocket, logging.getLogger()))
