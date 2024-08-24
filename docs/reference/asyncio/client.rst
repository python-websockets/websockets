Client (new :mod:`asyncio`)
===========================

.. automodule:: websockets.asyncio.client

Opening a connection
--------------------

.. autofunction:: connect
    :async:

.. autofunction:: unix_connect
    :async:

.. autofunction:: process_exception

Using a connection
------------------

.. autoclass:: ClientConnection

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
