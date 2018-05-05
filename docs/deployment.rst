Deployment
==========

.. currentmodule:: websockets

Application server
------------------

The author of ``websockets`` isn't aware of best practices for deploying
network services based on :mod:`asyncio`, let alone application servers.

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
with the object returned by :func:`~server.serve`:

- using it as a asynchronous context manager, or
- calling its ``close()`` method, then waiting for its ``wait_closed()``
  method to complete.

Tasks that handle connections will be cancelled. For example, if the handler
is awaiting :meth:`~protocol.WebSocketCommonProtocol.recv`, that call will
raise :exc:`~asyncio.CancelledError`.

On Unix systems, shutdown is usually triggered by sending a signal.

Here's a full example (Unix-only):

.. literalinclude:: ../example/shutdown.py
    :emphasize-lines: 13,17-19

``async`` and ``await`` were introduced in Python 3.5. websockets supports
asynchronous context managers on Python ≥ 3.5.1. ``async for`` was introduced
in Python 3.6. Here's the equivalent for older Python versions:

.. literalinclude:: ../example/old_shutdown.py
    :emphasize-lines: 22-25

It's more difficult to achieve the same effect on Windows. Some third-party
projects try to help with this problem.

If your server doesn't run in the main thread, look at
:func:`~asyncio.AbstractEventLoop.call_soon_threadsafe`.

Memory use
----------

In order to avoid excessive memory use caused by buffer bloat, it is strongly
recommended to :ref:`tune buffer sizes <buffers>`.

Most importantly ``max_size`` should be lowered according to the expected size
of messages. It is also suggested to lower ``max_queue``, ``read_limit`` and
``write_limit`` if memory use is a concern.

Port sharing
------------

The WebSocket protocol is an extension of HTTP/1.1. It can be tempting to
serve both HTTP and WebSocket on the same port.

The author of ``websockets`` doesn't think that's a good idea, due to the
widely different operational characteristics of HTTP and WebSocket.

``websockets`` provide minimal support for responding to HTTP requests with
the :meth:`~server.WebSocketServerProtocol.process_request()` hook. Typical
use cases include health checks. Here's an example:

.. literalinclude:: ../example/health_check_server.py
    :emphasize-lines: 9-13,19-20
