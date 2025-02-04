Server (:mod:`threading`)
=========================

.. automodule:: websockets.sync.server

Creating a server
-----------------

.. autofunction:: serve

.. autofunction:: unix_serve

Routing connections
-------------------

.. automodule:: websockets.sync.router

.. autofunction:: route

.. autofunction:: unix_route

.. autoclass:: Router

.. currentmodule:: websockets.sync.server

Routing connections
-------------------

.. autofunction:: route
    :async:

.. autofunction:: unix_route
    :async:

.. autoclass:: Server


Running a server
----------------

.. autoclass:: Server

    .. automethod:: serve_forever

    .. automethod:: shutdown

    .. automethod:: fileno

Using a connection
------------------

.. autoclass:: ServerConnection

    .. automethod:: __iter__

    .. automethod:: recv

    .. automethod:: recv_streaming

    .. automethod:: send

    .. automethod:: close

    .. automethod:: ping

    .. automethod:: pong

    .. automethod:: respond

    WebSocket connection objects also provide these attributes:

    .. autoattribute:: id

    .. autoattribute:: logger

    .. autoproperty:: local_address

    .. autoproperty:: remote_address

    .. autoproperty:: latency

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
