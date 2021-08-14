Utilities
=========

Broadcast
---------

.. autofunction:: websockets.broadcast

WebSocket events
----------------

.. automodule:: websockets.frames

    .. autoclass:: Frame

    .. autoclass:: Opcode

    .. autoclass:: Close

HTTP events
-----------

.. automodule:: websockets.http11

    .. autoclass:: Request

    .. autoclass:: Response

.. automodule:: websockets.datastructures

    .. autoclass:: Headers

        .. automethod:: get_all

        .. automethod:: raw_items

    .. autoexception:: MultipleValuesError
