Deployment
==========

.. currentmodule:: websockets

Application server
------------------

The author of websockets isn't aware of best practices for deploying network
services based on :mod:`asyncio`, let alone application servers.

You can run a script similar to the :ref:`server example <server-example>`,
inside a supervisor if you deem that useful.

You can also add a wrapper to daemonize the process. Third-party libraries
provide solutions for that.

If you can share knowledge on this topic, please file an issue_. Thanks!

.. _issue: https://github.com/aaugustin/websockets/issues/new

Graceful shutdown
-----------------

You may want to close connections gracefully when shutting down the server,
perhaps after executing some cleanup logic. There are two ways to achieve this
with the object returned by :func:`~legacy.server.serve`:

- using it as a asynchronous context manager, or
- calling its ``close()`` method, then waiting for its ``wait_closed()``
  method to complete.

On Unix systems, shutdown is usually triggered by sending a signal.

Here's a full example for handling SIGTERM on Unix:

.. literalinclude:: ../../example/shutdown_server.py
    :emphasize-lines: 12-15,17

This example is easily adapted to handle other signals. If you override the
default handler for SIGINT, which raises :exc:`KeyboardInterrupt`, be aware
that you won't be able to interrupt a program with Ctrl-C anymore when it's
stuck in a loop.

It's more difficult to achieve the same effect on Windows. Some third-party
projects try to help with this problem.

If your server doesn't run in the main thread, look at
:func:`~asyncio.AbstractEventLoop.call_soon_threadsafe`.

Memory usage
------------

.. _memory-usage:

In most cases, memory usage of a WebSocket server is proportional to the
number of open connections. When a server handles thousands of connections,
memory usage can become a bottleneck.

Memory usage of a single connection is the sum of:

1. the baseline amount of memory websockets requires for each connection,
2. the amount of data held in buffers before the application processes it,
3. any additional memory allocated by the application itself.

Baseline
........

.. _compression-settings:

Compression settings are the main factor affecting the baseline amount of
memory used by each connection.

If you'd like to customize compression settings, here are the main knobs.

- Context Takeover is necessary to get good performance for almost all
  applications. It should remain enabled.
- Window Bits is a trade-off between memory usage and compression rate.
  It should be an integer between 9 (lowest memory usage) and 15 (highest
  compression rate). Setting it to 8 is possible but triggers a bug in some
  versions of zlib.
- Memory Level is a trade-off between memory usage and compression speed.
  However, a lower memory level can increase speed thanks to memory locality,
  even if the CPU does more work! It should be an integer between 1 (lowest
  memory usage) and 9 (highest compression speed in theory, not in practice).

By default, websockets enables compression with conservative settings that
optimize memory usage at the cost of a slightly worse compression rate: Window
Bits = 12 and Memory Level = 5. This strikes a good balance for small messages
that are typical of WebSocket servers.

If you'd like to configure different compression settings, see this
:ref:`example <per-message-deflate-configuration-example>`. If you don't set
limits on Window Bits and neither does the remote endpoint, it defaults to the
maximum value of 15. If you don't set Memory Level, it defaults to 8 — more
accurately, to ``zlib.DEF_MEM_LEVEL`` which is 8.

Here's how various compression settings affect memory usage of a single
connection on a 64-bit system, as well a benchmark of compressed size and
compression time for a corpus of small JSON documents.

+-------------+-------------+--------------+--------------+------------------+------------------+
| Compression | Window Bits | Memory Level | Memory usage | Size vs. default | Time vs. default |
+=============+=============+==============+==============+==================+==================+
|             | 15          | 8            | 322 KiB      | -4.0%            | +15%             +
+-------------+-------------+--------------+--------------+------------------+------------------+
|             | 14          | 7            | 178 KiB      | -2.6%            | +10%             |
+-------------+-------------+--------------+--------------+------------------+------------------+
|             | 13          | 6            | 106 KiB      | -1.4%            | +5%              |
+-------------+-------------+--------------+--------------+------------------+------------------+
| *default*   | 12          | 5            | 70 KiB       | =                | =                |
+-------------+-------------+--------------+--------------+------------------+------------------+
|             | 11          | 4            | 52 KiB       | +3.7%            | -5%              |
+-------------+-------------+--------------+--------------+------------------+------------------+
|             | 10          | 3            | 43 KiB       | +90%             | +50%             |
+-------------+-------------+--------------+--------------+------------------+------------------+
|             | 9           | 2            | 39 KiB       | +160%            | +100%            |
+-------------+-------------+--------------+--------------+------------------+------------------+
| *disabled*  | N/A         | N/A          | 19 KiB       | N/A              | N/A              |
+-------------+-------------+--------------+--------------+------------------+------------------+

*Don't assume this example is representative! Compressed size and compression
time depend heavily on the kind of messages exchanged by the application!*

You can adapt the `compression.py`_ benchmark for your application by creating
a list of typical messages and passing it to the ``_benchmark`` function.

.. _compression.py: https://github.com/aaugustin/websockets/blob/main/performance/compression.py

This `blog post by Ilya Grigorik`_ provides more details about how compression
settings affect memory usage and how to optimize them.

.. _blog post by Ilya Grigorik: https://www.igvita.com/2013/11/27/configuring-and-optimizing-websocket-compression/

This `experiment by Peter Thorson`_ suggests Window Bits = 11 and Memory Level =
4 as a sweet spot for optimizing memory usage.

.. _experiment by Peter Thorson: https://www.ietf.org/mail-archive/web/hybi/current/msg10222.html

websockets defaults to Window Bits = 12 and Memory Level = 5 in order to stay
away from Window Bits = 10 or Memory Level = 3, where performance craters in
the benchmark. This raises doubts on what could happen at Window Bits = 11 and
Memory Level = 4 on a different set of messages. The defaults needs to be safe
for all applications, hence a more conservative choice.

Buffers
.......

Under normal circumstances, buffers are almost always empty.

Under high load, if a server receives more messages than it can process,
bufferbloat can result in excessive memory use.

By default websockets has generous limits. It is strongly recommended to adapt
them to your application. When you call :func:`~legacy.server.serve`:

- Set ``max_size`` (default: 1 MiB, UTF-8 encoded) to the maximum size of
  messages your application generates.
- Set ``max_queue`` (default: 32) to the maximum number of messages your
  application expects to receive faster than it can process them. The queue
  provides burst tolerance without slowing down the TCP connection.

Furthermore, you can lower ``read_limit`` and ``write_limit`` (default:
64 KiB) to reduce the size of buffers for incoming and outgoing data.

The design document provides :ref:`more details about buffers<buffers>`.

Port sharing
------------

The WebSocket protocol is an extension of HTTP/1.1. It can be tempting to
serve both HTTP and WebSocket on the same port.

The author of websockets doesn't think that's a good idea, due to the widely
different operational characteristics of HTTP and WebSocket.

websockets provide minimal support for responding to HTTP requests with the
:meth:`~legacy.server.WebSocketServerProtocol.process_request` hook. Typical
use cases include health checks. Here's an example:

.. literalinclude:: ../../example/health_check_server.py
    :emphasize-lines: 9-11,20
