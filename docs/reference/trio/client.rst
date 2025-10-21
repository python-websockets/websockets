Client (:mod:`trio`)
=======================

.. admonition:: The :mod:`trio` API is experimental.
    :class: caution

    Please provide feedback in GitHub issues about the API, especially if you
    believe there's a more intuitive or convenient way to connect to a server.

.. automodule:: websockets.trio.client

Opening a connection
--------------------

.. autofunction:: connect
    :async:

.. autofunction:: process_exception

Using a connection
------------------

.. autoclass:: ClientConnection

    .. automethod:: __aiter__

    .. automethod:: recv

    .. automethod:: recv_streaming

    .. automethod:: send

    .. automethod:: aclose

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
