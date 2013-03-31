WebSockets
==========

``websockets`` is an implementation of `RFC 6455`_, the WebSocket protocol,
with a focus on simplicity and correctness.

It relies on the `Tulip`_ library, which prefigurates Python's `asynchronous
IO support`_, and requires Python ≥ 3.3.

.. _RFC 6455: http://tools.ietf.org/html/rfc6455
.. _Tulip: http://code.google.com/p/tulip/
.. _asynchronous IO support: http://www.python.org/dev/peps/pep-3156/

Example
=======

Here's a WebSocket server example. It reads a name from the client and sends a
greeting.

.. literalinclude:: ../example/server.py

Here's a corresponding client example.

.. literalinclude:: ../example/client.py

Design
======

The WebSocket protocol contains two phases:

1. An opening handshake, in the form of an HTTP Upgrade request;
2. Data transfer, as framed messages, ending with a closing handshake.

The first phase is designed to integrate with existing HTTP software.
``websockets`` provides functions to build and validate the request and the
response headers.

The second phase is the core of the WebSocket protocol. ``websockets``
provides a standalone implementation on top of Tulip.

Finally, ``websockets`` contains sample client and server implementations
showing how these pieces fit together.

API
===

Opening handshake
-----------------

.. automodule:: websockets.handshake
   :members:

Data transfer
-------------

.. automodule:: websockets.framing
   :members:

URI parser
----------

.. automodule:: websockets.uri
   :members:

Sample implementations
======================

Client
------

.. automodule:: websockets.client
   :members:

Server
------

.. automodule:: websockets.server
   :members:

HTTP utilities
--------------

.. automodule:: websockets.http
   :members:

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
