Exceptions
==========

.. automodule:: websockets.exceptions

.. autoexception:: WebSocketException

Connection closed
-----------------

:meth:`~websockets.asyncio.connection.Connection.recv`,
:meth:`~websockets.asyncio.connection.Connection.send`, and similar methods
raise the exceptions below when the connection is closed. This is the expected
way to detect disconnections.

.. autoexception:: ConnectionClosed

.. autoexception:: ConnectionClosedOK

.. autoexception:: ConnectionClosedError

Connection failed
-----------------

These exceptions are raised by :func:`~websockets.asyncio.client.connect` when
the opening handshake fails and the connection cannot be established. They are
also reported by :func:`~websockets.asyncio.server.serve` in logs.

.. autoexception:: InvalidURI

.. autoexception:: InvalidHandshake

.. autoexception:: InvalidMessage

.. autoexception:: SecurityError

.. autoexception:: InvalidStatus

.. autoexception:: InvalidHeader

.. autoexception:: InvalidHeaderFormat

.. autoexception:: InvalidHeaderValue

.. autoexception:: InvalidOrigin

.. autoexception:: InvalidUpgrade

.. autoexception:: NegotiationError

.. autoexception:: DuplicateParameter

.. autoexception:: InvalidParameterName

.. autoexception:: InvalidParameterValue

Sans-I/O exceptions
-------------------

These exceptions are only raised by the Sans-I/O implementation. They are
translated to :exc:`ConnectionClosedError` in the other implementations.

.. autoexception:: ProtocolError

.. autoexception:: PayloadTooBig

.. autoexception:: InvalidState

Miscellaneous exceptions
------------------------

.. autoexception:: ConcurrencyError

Legacy exceptions
-----------------

These exceptions are only used by the legacy :mod:`asyncio` implementation.

.. autoexception:: InvalidStatusCode

.. autoexception:: AbortHandshake

.. autoexception:: RedirectHandshake
