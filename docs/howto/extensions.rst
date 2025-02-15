Write an extension
==================

.. currentmodule:: websockets

During the opening handshake, WebSocket clients and servers negotiate which
extensions_ will be used and with which parameters.

.. _extensions: https://datatracker.ietf.org/doc/html/rfc6455.html#section-9

Then, each frame is processed before being sent and after being received
according to the extensions that were negotiated.

Writing an extension requires implementing at least two classes, an extension
factory and an extension. They inherit from base classes provided by websockets.

Extension factory
-----------------

An extension factory negotiates parameters and instantiates the extension.

Clients and servers require separate extension factories with distinct APIs.
Base classes are :class:`~extensions.ClientExtensionFactory` and
:class:`~extensions.ServerExtensionFactory`.

Extension factories are the public API of an extension. Extensions are enabled
with the ``extensions`` parameter of :func:`~asyncio.client.connect` or
:func:`~asyncio.server.serve`.

Extension
---------

An extension decodes incoming frames and encodes outgoing frames.

If the extension is symmetrical, clients and servers can use the same class. The
base class is :class:`~extensions.Extension`.

Since extensions are initialized by extension factories, they don't need to be
part of the public API of an extension.
