Extensions
==========

.. currentmodule:: websockets.extensions

The WebSocket protocol supports extensions_.

At the time of writing, there's only one `registered extension`_ with a public
specification, WebSocket Per-Message Deflate.

.. _extensions: https://datatracker.ietf.org/doc/html/rfc6455.html#section-9
.. _registered extension: https://www.iana.org/assignments/websocket/websocket.xhtml#extension-name

Per-Message Deflate
-------------------

.. automodule:: websockets.extensions.permessage_deflate

:mod:`websockets.extensions.permessage_deflate` implements WebSocket Per-Message
Deflate.

This extension is specified in :rfc:`7692`.

Refer to the :doc:`topic guide on compression <../topics/compression>` to learn
more about tuning compression settings.

.. autoclass:: ServerPerMessageDeflateFactory

.. autoclass:: ClientPerMessageDeflateFactory

Base classes
------------

.. automodule:: websockets.extensions

:mod:`websockets.extensions` defines base classes for implementing extensions.

Refer to the :doc:`how-to guide on extensions <../howto/extensions>` to learn
more about writing an extension.

.. autoclass:: Extension

    .. autoattribute:: name

    .. automethod:: decode

    .. automethod:: encode

.. autoclass:: ServerExtensionFactory

    .. automethod:: process_request_params

.. autoclass:: ClientExtensionFactory

    .. autoattribute:: name

    .. automethod:: get_request_params

    .. automethod:: process_response_params
