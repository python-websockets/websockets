FAQ
===

.. currentmodule:: websockets

.. note::

    Many questions asked in websockets' issue tracker are actually
    about :mod:`asyncio`. Python's documentation about `developing with
    asyncio`_ is a good complement.

    .. _developing with asyncio: https://docs.python.org/3/library/asyncio-dev.html

Server side
-----------

Why does my server close the connection prematurely?
....................................................

Your connection handler exits prematurely. Wait for the work to be finished
before returning.

For example, if your handler has a structure similar to::

    async def handler(websocket):
        asyncio.create_task(do_some_work())

change it to::

    async def handler(websocket):
        await do_some_work()

Why does the server close the connection after processing one message?
......................................................................

Your connection handler exits after processing one message. Write a loop to
process multiple messages.

For example, if your handler looks like this::

    async def handler(websocket):
        print(websocket.recv())

change it like this::

    async def handler(websocket):
        async for message in websocket:
            print(message)

*Don't feel bad if this happens to you — it's the most common question in
websockets' issue tracker :-)*

Why can only one client connect at a time?
..........................................

Your connection handler blocks the event loop. Look for blocking calls.
Any call that may take some time must be asynchronous.

For example, if you have::

    async def handler(websocket):
        time.sleep(1)

change it to::

    async def handler(websocket):
        await asyncio.sleep(1)

This is part of learning asyncio. It isn't specific to websockets.

See also Python's documentation about `running blocking code`_.

.. _running blocking code: https://docs.python.org/3/library/asyncio-dev.html#running-blocking-code

How can I pass additional arguments to the connection handler?
..............................................................

You can bind additional arguments to the connection handler with
:func:`functools.partial`::

    import asyncio
    import functools
    import websockets

    async def handler(websocket, extra_argument):
        ...

    bound_handler = functools.partial(handler, extra_argument='spam')
    start_server = websockets.serve(bound_handler, ...)

Another way to achieve this result is to define the ``handler`` coroutine in
a scope where the ``extra_argument`` variable exists instead of injecting it
through an argument.

How do I get access HTTP headers, for example cookies?
......................................................

To access HTTP headers during the WebSocket handshake, you can override
:attr:`~server.WebSocketServerProtocol.process_request`::

    async def process_request(self, path, request_headers):
        cookies = request_header["Cookie"]

Once the connection is established, they're available in
:attr:`~server.WebSocketServerProtocol.request_headers`::

    async def handler(websocket):
        cookies = websocket.request_headers["Cookie"]

How do I get the IP address of the client connecting to my server?
..................................................................

It's available in :attr:`~legacy.protocol.WebSocketCommonProtocol.remote_address`::

    async def handler(websocket):
        remote_ip = websocket.remote_address[0]

How do I set which IP addresses my server listens to?
.....................................................

Look at the ``host`` argument of :meth:`~asyncio.loop.create_server`.

:func:`~server.serve` accepts the same arguments as
:meth:`~asyncio.loop.create_server`.

How do I close a connection properly?
.....................................

websockets takes care of closing the connection when the handler exits.

How do I run a HTTP server and WebSocket server on the same port?
.................................................................

You don't.

HTTP and WebSockets have widely different operational characteristics.
Running them on the same server is a bad idea.

Providing a HTTP server is out of scope for websockets. It only aims at
providing a WebSocket server.

There's limited support for returning HTTP responses with the
:attr:`~server.WebSocketServerProtocol.process_request` hook.

If you need more, pick a HTTP server and run it separately.

Client side
-----------

Why does my client close the connection prematurely?
....................................................

You're exiting the context manager prematurely. Wait for the work to be
finished before exiting.

For example, if your code has a structure similar to::

    async with connect(...) as websocket:
        asyncio.create_task(do_some_work())

change it to::

    async with connect(...) as websocket:
        await do_some_work()

How do I close a connection properly?
.....................................

The easiest is to use :func:`~client.connect` as a context manager::

    async with connect(...) as websocket:
        ...

How do I reconnect automatically when the connection drops?
...........................................................

See `issue 414`_.

.. _issue 414: https://github.com/aaugustin/websockets/issues/414

How do I stop a client that is continuously processing messages?
................................................................

You can close the connection.

Here's an example that terminates cleanly when it receives SIGTERM on Unix:

.. literalinclude:: ../../example/shutdown_client.py
    :emphasize-lines: 10-13

How do I disable TLS/SSL certificate verification?
..................................................

Look at the ``ssl`` argument of :meth:`~asyncio.loop.create_connection`.

:func:`~client.connect` accepts the same arguments as
:meth:`~asyncio.loop.create_connection`.

asyncio usage
-------------

How do I do two things in parallel? How do I integrate with another coroutine?
..............................................................................

You must start two tasks, which the event loop will run concurrently. You can
achieve this with :func:`asyncio.gather` or :func:`asyncio.create_task`.

Keep track of the tasks and make sure they terminate or you cancel them when
the connection terminates.

Why does my program never receives any messages?
................................................

Your program runs a coroutine that never yields control to the event loop. The
coroutine that receives messages never gets a chance to run.

Putting an ``await`` statement in a ``for`` or a ``while`` loop isn't enough
to yield control. Awaiting a coroutine may yield control, but there's no
guarantee that it will.

For example, :meth:`~legacy.protocol.WebSocketCommonProtocol.send` only yields
control when send buffers are full, which never happens in most practical
cases.

If you run a loop that contains only synchronous operations and
a :meth:`~legacy.protocol.WebSocketCommonProtocol.send` call, you must yield
control explicitly with :func:`asyncio.sleep`::

    async def producer(websocket):
        message = generate_next_message()
        await websocket.send(message)
        await asyncio.sleep(0)  # yield control to the event loop

:func:`asyncio.sleep` always suspends the current task, allowing other tasks
to run. This behavior is documented precisely because it isn't expected from
every coroutine.

See `issue 867`_.

.. _issue 867: https://github.com/aaugustin/websockets/issues/867

Why does my very simple program misbehave mysteriously?
.......................................................

You are using :func:`time.sleep` instead of :func:`asyncio.sleep`, which
blocks the event loop and prevents asyncio from operating normally.

This may lead to messages getting send but not received, to connection
timeouts, and to unexpected results of shotgun debugging e.g. adding an
unnecessary call to :meth:`~legacy.protocol.WebSocketCommonProtocol.send`
makes the program functional.

Both sides
----------

What does ``ConnectionClosedError: no close frame received or sent`` mean?
..........................................................................

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
.......................................................................................................................

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
................................................................................

Use :func:`~asyncio.wait_for`::

    await asyncio.wait_for(websocket.recv(), timeout=10)

This technique works for most APIs, except for asynchronous context managers.
See `issue 574`_.

.. _issue 574: https://github.com/aaugustin/websockets/issues/574

How can I pass additional arguments to a custom protocol subclass?
..................................................................

You can bind additional arguments to the protocol factory with
:func:`functools.partial`::

    import asyncio
    import functools
    import websockets

    class MyServerProtocol(websockets.WebSocketServerProtocol):
        def __init__(self, extra_argument, *args, **kwargs):
            super().__init__(*args, **kwargs)
            # do something with extra_argument

    create_protocol = functools.partial(MyServerProtocol, extra_argument='spam')
    start_server = websockets.serve(..., create_protocol=create_protocol)

This example was for a server. The same pattern applies on a client.

How do I keep idle connections open?
....................................

websockets sends pings at 20 seconds intervals to keep the connection open.

It closes the connection if it doesn't get a pong within 20 seconds.

You can adjust this behavior with ``ping_interval`` and ``ping_timeout``.

How do I respond to pings?
..........................

websockets takes care of responding to pings with pongs.

Miscellaneous
-------------

How do I create channels or topics?
...................................

websockets doesn't have built-in publish / subscribe for these use cases.

Depending on the scale of your service, a simple in-memory implementation may
do the job or you may need an external publish / subscribe component.

Can I use websockets synchronously, without ``async`` / ``await``?
..................................................................

You can convert every asynchronous call to a synchronous call by wrapping it
in ``asyncio.get_event_loop().run_until_complete(...)``. Unfortunately, this
is deprecated as of Python 3.10.

If this turns out to be impractical, you should use another library.

Are there ``onopen``, ``onmessage``, ``onerror``, and ``onclose`` callbacks?
............................................................................

No, there aren't.

websockets provides high-level, coroutine-based APIs. Compared to callbacks,
coroutines make it easier to manage control flow in concurrent code.

If you prefer callback-based APIs, you should use another library.

Why do I get the error: ``module 'websockets' has no attribute '...'``?
.......................................................................

Often, this is because you created a script called ``websockets.py`` in your
current working directory. Then ``import websockets`` imports this module
instead of the websockets library.

I'm having problems with threads
................................

You shouldn't use threads. Use tasks instead.

:meth:`~asyncio.loop.call_soon_threadsafe` may help.
