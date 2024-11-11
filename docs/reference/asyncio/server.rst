Server (new :mod:`asyncio`)
===========================

.. automodule:: websockets.asyncio.server

Creating a server
-----------------

.. autofunction:: serve
    :async:

.. autofunction:: unix_serve
    :async:

Running a server
----------------

.. autoclass:: Server

    .. autoattribute:: connections

    .. automethod:: close

    .. automethod:: wait_closed

    .. automethod:: get_loop

    .. automethod:: is_serving

    .. automethod:: start_serving

    .. automethod:: serve_forever

    .. autoattribute:: sockets

Using a connection
------------------

.. autoclass:: ServerConnection

    .. automethod:: __aiter__

    .. automethod:: recv

    .. automethod:: recv_streaming

    .. automethod:: send

    .. automethod:: close

    .. automethod:: wait_closed

    .. automethod:: ping

    .. automethod:: pong

    .. automethod:: respond

    WebSocket connection objects also provide these attributes:

    .. autoattribute:: id

    .. autoattribute:: logger

    .. autoproperty:: local_address

    .. autoproperty:: remote_address

    .. autoattribute:: latency

    .. autoproperty:: state

    The following attributes are available after the opening handshake,
    once the WebSocket connection is open:

    .. autoattribute:: request

    .. autoattribute:: response

    .. autoproperty:: subprotocol

    The following attributes are available after the closing handshake,
    once the WebSocket connection is closed:

    .. autoproperty:: close_code

    .. autoproperty:: close_reason

Broadcast
---------

.. autofunction:: websockets.asyncio.server.broadcast

HTTP Basic Authentication
-------------------------

websockets supports HTTP Basic Authentication according to
:rfc:`7235` and :rfc:`7617`.

.. autofunction:: websockets.asyncio.server.basic_auth
