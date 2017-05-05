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
perhaps after executing some cleanup logic.

The proper way to do this is to call the ``close()`` method of the object
returned by :func:`~websockets.server.serve`, then wait for ``wait_closed()``
to complete.

Tasks that handle connections will be cancelled, in the sense that
:meth:`~websockets.protocol.WebSocketCommonProtocol.recv` raises
:exc:`~asyncio.CancelledError`.

On Unix systems, shutdown is usually triggered by sending a signal.

Here's a full example (Unix-only):

.. literalinclude:: ../example/shutdown.py


It's more difficult to achieve the same effect on Windows. Some third-party
projects try to help with this problem.

If your server doesn't run in the main thread, look at
:func:`~asyncio.AbstractEventLoop.call_soon_threadsafe`.
