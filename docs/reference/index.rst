API reference
=============

.. currentmodule:: websockets

:mod:`asyncio`
--------------

This is the default implementation. It's ideal for servers that handle many
clients concurrently.

.. toctree::
   :titlesonly:

   asyncio/server
   asyncio/client
   asyncio/common

:mod:`threading`
----------------

This alternative implementation can be a good choice for clients.

.. toctree::
   :titlesonly:

   sync/server
   sync/client
   sync/common

`Sans-I/O`_
-----------

This layer is designed for integrating in third-party libraries, typically
application servers.

.. _Sans-I/O: https://sans-io.readthedocs.io/

.. toctree::
   :titlesonly:

   sansio/server
   sansio/client
   sansio/common

Extensions
----------

The Per-Message Deflate extension is built in. You may also define custom
extensions.

.. toctree::
   :titlesonly:

   extensions

Shared
------

These low-level API are shared by all implementations.

.. toctree::
   :titlesonly:

   datastructures
   exceptions
   types

API stability
-------------

Public API documented in this API reference are subject to the
:ref:`backwards-compatibility policy <backwards-compatibility policy>`.

Anything that isn't listed in the API reference is a private API. There's no
guarantees of behavior or backwards-compatibility for private APIs.

Convenience imports
-------------------

For convenience, many public APIs can be imported directly from the
``websockets`` package.


.. admonition:: Convenience imports are incompatible with some development tools.
    :class: caution

    Specifically, static code analysis tools don't understand them. This breaks
    auto-completion and contextual documentation in IDEs, type checking with
    mypy_, etc.

    .. _mypy: https://github.com/python/mypy

    If you're using such tools, stick to the full import paths, as explained in
    this FAQ: :ref:`real-import-paths`

Limitations
-----------

There are a few known limitations in the current API.

.. toctree::
   :titlesonly:

   limitations
