Deployment
==========

Backpressure
------------

.. note::

    This section discusses the concept of backpressure from the perspective of
    a server but the concepts also apply to clients. The issue is symmetrical.

With a naive implementation, if a server receives inputs faster than it can
process them, or if it generates outputs faster than it can send them, data
accumulates in buffers, eventually causing the server to run out of memory and
crash.

The solution to this problem is backpressure. Any part of the server that
receives inputs faster than it can it can process them and send the outputs
must propagate that information back to the previous part in the chain.

``websockets`` is designed to make it easy to get backpressure right.

For incoming data, ``websockets`` builds upon :class:`~asyncio.StreamReader`
which propagates backpressure to its own buffer and to the TCP stream. Frames
are parsed from the input stream and added to a bounded queue. If the queue
fills up, parsing halts until some the application reads a frame.

For outgoing data, ``websockets`` builds upon :class:`~asyncio.StreamWriter`
which implements flow control. If the output buffers grow too large, it waits
until they're drained. That's why all APIs that write frames are asynchronous
in websockets (since version 2.0).

Of course, it's still possible for an application to create its own unbounded
buffers and break the backpressure. Be careful with queues.

Buffers
-------

An asynchronous systems works best when its buffers are almost always empty.

For example, if a client sends frames too fast for a server, the queue of
incoming frames will be constantly full. The server will always be 32 frames
(by default) behind the client. This consumes memory and adds latency for no
good reason.

If buffers are almost always full and that problem cannot be solved by adding
capacity (typically because the system is bottlenecked by the output and
constantly regulated by backpressure), reducing the size of buffers minimizes
negative consequences.

By default ``websockets`` has rather high limits. You can decrease them
according to your application's characteristics.

Bufferbloat can happen at every level in the stack where there is a buffer.
The receiving side contains these buffers:

- OS buffers: you shouldn't need to tune them in general.
- :class:`~asyncio.StreamReader` bytes buffer: the default limit is 64kB.
  You can set another limit by passing a ``read_limit`` keyword argument to
  :func:`~websockets.client.connect` or :func:`~websockets.server.serve`.
- ``websockets`` frame buffer: its size depends both on the size and the
  number of frames it contains. By default the maximum size is 1MB and the
  maximum number is 32. You can adjust these limits by setting the
  ``max_size`` and ``max_queue`` keyword arguments of
  :func:`~websockets.client.connect` or :func:`~websockets.server.serve`.

The sending side contains these buffers:

- :class:`~asyncio.StreamWriter` bytes buffer: the default size is 64kB.
  You can set another limit by passing a ``write_limit`` keyword argument to
  :func:`~websockets.client.connect` or :func:`~websockets.server.serve`.
- OS buffers: you shouldn't need to tune them in general.

Deployment
----------

The author of ``websockets`` isn't aware of best practices for deploying
network services based on :mod:`asyncio`.

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
with the object returned by :func:`~websockets.server.serve`:

- using it as a asynchronous context manager, or
- calling its ``close()`` method, then waiting for its ``wait_closed()``
  method to complete.

Tasks that handle connections will be cancelled, in the sense that
:meth:`~websockets.protocol.WebSocketCommonProtocol.recv` raises
:exc:`~asyncio.CancelledError`.

On Unix systems, shutdown is usually triggered by sending a signal.

Here's a full example (Unix-only):

.. literalinclude:: ../example/shutdown.py

``async``, ``await``, and asynchronous context managers aren't available in
Python < 3.5. Here's the equivalent for older Python versions:

.. literalinclude:: ../example/oldshutdown.py

It's more difficult to achieve the same effect on Windows. Some third-party
projects try to help with this problem.

If your server doesn't run in the main thread, look at
:func:`~asyncio.AbstractEventLoop.call_soon_threadsafe`.

Port sharing
------------

The WebSocket protocol is an extension of HTTP/1.1. It can be tempting to
serve both HTTP and WebSocket on the same port.

The author of ``websockets`` doesn't think that's a good idea, due to the
widely different operational characteristics of HTTP and WebSocket.

If you need to respond to requests with a protocol other than WebSocket, for
example TCP or HTTP health checks, run a server for that protocol on another
port, within the same Python process, with :func:`~asyncio.start_server`.
