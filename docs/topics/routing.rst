Routing
=======

.. currentmodule:: websockets

Many WebSocket servers provide just one endpoint. That's why
:func:`~asyncio.server.serve` accepts a single connection handler as its first
argument.

This may come as a surprise to you if you're used to HTTP servers. In a standard
HTTP application, each request gets dispatched to a handler based on the request
path. Clients know which path to use for which operation.

In a WebSocket application, clients open a persistent connection then they send
all messages over that unique connection. When different messages correspond to
different operations, they must be dispatched based on the message content.

Simple routing
--------------

If you need different handlers for different clients or different use cases, you
may route each connection to the right handler based on the request path.

Since WebSocket servers typically provide fewer routes than HTTP servers, you
can keep it simple::

    async def handler(websocket):
        match websocket.request.path:
            case "/blue":
                await blue_handler(websocket)
            case "/green":
                await green_handler(websocket)
            case _:
                # No handler for this path. Close the connection.
                return

You may also route connections based on the first message received from the
client, as demonstrated in the :doc:`tutorial <../intro/tutorial2>`::

    import json

    async def handler(websocket):
        message = await websocket.recv()
        settings = json.loads(message)
        match settings["color"]:
            case "blue":
                await blue_handler(websocket)
            case "green":
                await green_handler(websocket)
            case _:
                # No handler for this message. Close the connection.
                return

When you need to authenticate the connection before routing it, this pattern is
more convenient.

Complex routing
---------------

If you have outgrow these simple patterns, websockets provides full-fledged
routing based on the request path with :func:`~asyncio.router.route`.

This feature builds upon Flask_'s router. To use it, you must install the
third-party library `werkzeug`_:

.. code-block:: console

    $ pip install werkzeug

.. _Flask: https://flask.palletsprojects.com/
.. _werkzeug: https://werkzeug.palletsprojects.com/

:func:`~asyncio.router.route` expects a :class:`werkzeug.routing.Map` as its
first argument to declare which URL patterns map to which handlers. Review the
documentation of :mod:`werkzeug.routing` to learn about its functionality.

To give you a sense of what's possible, here's the URL map of the example in
`experiments/routing.py`_:

.. _experiments/routing.py: https://github.com/python-websockets/websockets/blob/main/experiments/routing.py

.. literalinclude:: ../../experiments/routing.py
    :start-at: url_map = Map(
    :end-at: await server.serve_forever()
