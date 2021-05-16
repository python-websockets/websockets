Extensions
==========

.. currentmodule:: websockets.extensions

The WebSocket protocol supports extensions_.

At the time of writing, there's only one `registered extension`_ with a public
specification, WebSocket Per-Message Deflate, specified in :rfc:`7692`.

.. _extensions: https://tools.ietf.org/html/rfc6455#section-9
.. _registered extension: https://www.iana.org/assignments/websocket/websocket.xhtml#extension-name

Per-Message Deflate
-------------------

.. automodule:: websockets.extensions.permessage_deflate

    .. autoclass:: ClientPerMessageDeflateFactory

    .. autoclass:: ServerPerMessageDeflateFactory

Abstract classes
----------------

.. automodule:: websockets.extensions

    .. autoclass:: Extension
        :members:

    .. autoclass:: ClientExtensionFactory
        :members:

    .. autoclass:: ServerExtensionFactory
        :members:

