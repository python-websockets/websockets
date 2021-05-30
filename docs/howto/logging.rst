Logging
=======

.. currentmodule:: websockets

Logs contents
-------------

When you run a WebSocket client, your code calls coroutines provided by
websockets.

If an error occurs, websockets tells you by raising an exception. For example,
it raises a :exc:`~exception.ConnectionClosed` exception if the other side
closes the connection.

When you run a WebSocket server, websockets accepts connections, performs the
opening handshake, runs the connection handler coroutine that you provided,
and performs the closing handshake.

Given this `inversion of control`_, if an error happens in the opening
handshake or if the connection handler crashes, there is no way to raise an
exception that you can handle.

.. _inversion of control: https://en.wikipedia.org/wiki/Inversion_of_control

Logs tell you about these errors.

Besides errors, you may want to record the activity of the server.

In a request/response protocol such as HTTP, there's an obvious way to record
activity: log one event per request/response. Unfortunately, this solution
doesn't work well for a bidirectional protocol such as WebSocket.

Instead, when running as a server, websockets logs one event when a
`connection is established`_ and another event when a `connection is
closed`_.

.. _connection is established: https://datatracker.ietf.org/doc/html/rfc6455#section-4
.. _connection is closed: https://datatracker.ietf.org/doc/html/rfc6455#section-7.1.4

websockets doesn't log an event for every message because that would be
excessive for many applications exchanging small messages at a fast rate.
However, you could add this level of logging in your own code if necessary.

See :ref:`log levels <log-levels>` below for details of events logged by
websockets at each level.

Configure logging
-----------------

websockets relies on the :mod:`logging` module from the standard library in
order to maximize compatibility and integrate nicely with other libraries::

    import logging

websockets logs to the ``"websockets.client"`` and ``"websockets.server"``
loggers.

websockets doesn't provide a default logging configuration because
requirements vary a lot depending on the environment.

Here's a basic configuration for a server in production::

    logging.basicConfig(
        format="%(asctime)s %(message)s",
        level=logging.INFO,
    )

Here's how to enable debug logs for development::

    logging.basicConfig(
        format="%(message)s",
        level=logging.DEBUG,
    )

You can select a different :class:`~logging.Logger` with the ``logger``
argument::

    import websockets

    async with websockets.serve(
        ...,
        logger=logging.getLogger("interface.websocket"),
    ):
        ...

Disable logging
---------------

If your application doesn't configure :mod:`logging`, Python outputs messages
of severity :data:`~logging.WARNING` and higher to :data:`~sys.stderr`. As a
consequence, you will see a message and a stack trace if a connection handler
coroutine crashes or if you hit a bug in websockets.

If you want to disable this behavior for websockets, you can add
a :class:`~logging.NullHandler`::

    logging.getLogger("websockets").addHandler(logging.NullHandler())

Additionally, if your application configures :mod:`logging`, you must disable
propagation to the root logger, or else its handlers could output logs::

    logging.getLogger("websockets").propagate = False

Alternatively, you could set the log level to :data:`~logging.CRITICAL` for
websockets, as the highest level currently used is :data:`~logging.ERROR`::

    logging.getLogger("websockets").setLevel(logging.CRITICAL)

Or you could configure a filter to drop all messages::

    logging.getLogger("websockets").addFilter(lambda record: None)

.. _log-levels:

Log levels
----------

Here's what websockets logs at each level.

:attr:`~logging.ERROR`
......................

* Exceptions raised by connection handler coroutines in servers
* Exceptions resulting from bugs in websockets

:attr:`~logging.INFO`
.....................

* Connections opened and closed in servers

:attr:`~logging.DEBUG`
......................

* Changes to the state of connections
* Handshake requests and responses
* All frames sent and received
* Steps to close a connection
* Keepalive pings and pongs
* Errors handled transparently

Debug messages have cute prefixes that make logs easier to scan:

* ``>`` - send something
* ``<`` - receive something
* ``=`` - set connection state
* ``x`` - shut down connection
* ``%`` - manage pings and pongs
* ``!`` - handle errors and timeouts
