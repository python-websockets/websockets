Server (:mod:`trio`)
=======================

.. automodule:: websockets.trio.server

Creating a server
-----------------

.. autofunction:: serve
    :async:

.. currentmodule:: websockets.trio.server

Running a server
----------------

.. autoclass:: Server

    .. autoattribute:: connections

    .. automethod:: aclose

    .. autoattribute:: listeners

Using a connection
------------------

.. autoclass:: ServerConnection

    .. automethod:: __aiter__

    .. automethod:: recv

    .. automethod:: recv_streaming

    .. automethod:: send

    .. automethod:: aclose

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

HTTP Basic Authentication
-------------------------

websockets supports HTTP Basic Authentication according to
:rfc:`7235` and :rfc:`7617`.

.. autofunction:: basic_auth
