"""
:mod:`websockets.extensions.base` exports abstract classes for implementing
extensions.

See `section 9 of RFC 6455`_.

.. _section 9 of RFC 6455: http://tools.ietf.org/html/rfc6455#section-9

"""

__all__ = ["Extension", "ClientExtensionFactory", "ServerExtensionFactory"]

from ..frames import ClientExtensionFactory, Extension, ServerExtensionFactory
