Server (:mod:`trio`)
=======================

.. admonition:: The :mod:`trio` API is experimental.
    :class: caution

    Please provide feedback in GitHub issues about the API, especially if you
    can propose a more intuitive or convenient way to start and stop a server.

.. automodule:: websockets.trio.server

Creating a server
-----------------

.. autofunction:: serve

.. admonition:: ``unix_serve`` is not available in the Trio implementation.
    :class: note

    This is because Trio `does not provide`_ ``open_unix_listeners`` yet.
    Instead, you can create Trio listeners using Unix domain sockets then
    call :func:`serve` with a ``listeners`` arguments.

    .. _does not provide: https://github.com/python-trio/trio/issues/279

Routing connections
-------------------

.. automodule:: websockets.trio.router

.. autofunction:: route

.. admonition:: ``unix_route`` is not available in the Trio implementation.
    :class: note

    This is because ``unix_serve`` isn't available either, as explained above.

.. autoclass:: Router

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

    .. automethod:: respond

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

Broadcast
---------

.. autofunction:: broadcast

HTTP Basic Authentication
-------------------------

websockets supports HTTP Basic Authentication according to
:rfc:`7235` and :rfc:`7617`.

.. autofunction:: basic_auth
