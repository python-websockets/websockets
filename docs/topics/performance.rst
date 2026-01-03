Performance
===========

.. currentmodule:: websockets

Here are tips to optimize performance.

TLS
---

You should terminate TLS in a reverse proxy rather than in a websockets server.

This will reduce memory usage of the websockets server and improve performance.

uvloop
------

You can make a websockets application faster by running it with uvloop_.

(This advice isn't specific to websockets. It applies to any :mod:`asyncio`
application.)

.. _uvloop: https://github.com/MagicStack/uvloop

broadcast
---------

:func:`~asyncio.server.broadcast` is the most efficient way to send a message to
many clients.
