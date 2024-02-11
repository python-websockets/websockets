Server (:mod:`asyncio` - new)
=============================

.. automodule:: websockets.asyncio.server

.. Creating a server
.. -----------------

.. .. autofunction:: serve
..     :async:

.. .. autofunction:: unix_serve
..     :async:

.. Running a server
.. ----------------

.. .. autoclass:: WebSocketServer

..     .. automethod:: serve_forever

..     .. automethod:: shutdown

..     .. automethod:: fileno

Using a connection
------------------

.. autoclass:: ServerConnection

    .. automethod:: __aiter__

    .. automethod:: recv

    .. automethod:: recv_streaming

    .. automethod:: send

    .. automethod:: close

    .. automethod:: ping

    .. automethod:: pong

    WebSocket connection objects also provide these attributes:

    .. autoattribute:: id

    .. autoattribute:: logger

    .. autoproperty:: local_address

    .. autoproperty:: remote_address

    The following attributes are available after the opening handshake,
    once the WebSocket connection is open:

    .. autoattribute:: request

    .. autoattribute:: response

    .. autoproperty:: subprotocol
