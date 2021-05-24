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

Compression settings are the main factor affecting the baseline amount of
memory used by each connection.

Read to the topic guide on :doc:`../topics/compression` to learn more about
tuning compression settings.

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
