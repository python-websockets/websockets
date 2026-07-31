Server (:mod:`asyncio`)
=======================

.. automodule:: websockets.asyncio.server

Creating a server
-----------------

.. autofunction:: serve
    :async:

.. autofunction:: unix_serve
    :async:

Routing connections
-------------------

.. automodule:: websockets.asyncio.router

.. autofunction:: route
    :async:

.. autofunction:: unix_route
    :async:

.. autoclass:: Router

.. currentmodule:: websockets.asyncio.server

Running a server
----------------

.. autoclass:: Server

    .. autoattribute:: connections

    .. automethod:: close

    .. automethod:: get_loop

    .. automethod:: start_serving

    .. automethod:: serve_forever

    .. automethod:: is_serving

    .. automethod:: wait_closed

    .. autoattribute:: sockets

Using a connection
------------------

.. autoclass:: ServerConnection

    .. automethod:: respond

    .. automethod:: __aiter__

    .. automethod:: recv

    .. automethod:: recv_streaming

    .. automethod:: send

    .. automethod:: close

    .. automethod:: wait_closed

    .. automethod:: ping

    .. automethod:: pong

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

.. autofunction:: broadcast

HTTP Basic Authentication
-------------------------

websockets supports HTTP Basic Authentication according to
:rfc:`7235` and :rfc:`7617`.

.. autofunction:: basic_auth
