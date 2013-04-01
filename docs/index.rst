.. module:: websockets

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
-------

.. _server-example:

Here's a WebSocket server example. It reads a name from the client and sends a
greeting.

.. literalinclude:: ../example/server.py

.. _client-example:

Here's a corresponding client example.

.. literalinclude:: ../example/client.py

Design
------

The WebSocket protocol contains two phases:

1. An opening handshake, in the form of an HTTP Upgrade request;
2. Data transfer, as framed messages, ending with a closing handshake.

The first phase is designed to integrate with existing HTTP software.
``websockets`` provides functions to build and validate the request and
response headers.

The second phase is the core of the WebSocket protocol. ``websockets``
provides a standalone implementation on top of Tulip with a very simple API.

``websockets`` also contains sample client and server implementations showing
how these pieces fit together.

The public APIs are described below. For convenience, they can be imported
directly from the :mod:`websockets` package, unless noted otherwise.

Main APIs
---------

Opening handshake
.................

.. automodule:: websockets.handshake
   :members:

Data transfer
.............

.. automodule:: websockets.framing
   :members:
   :inherited-members:

URI parser
..........

.. automodule:: websockets.uri
   :members:

Implementations
---------------

These sample implementations demonstrate how to tie together the opening
handshake and data transfer APIs.

Server
......

.. automodule:: websockets.server

   .. autofunction:: serve(ws_handler, host=None, port=None, **kwargs)

See also the :ref:`example <server-example>` above.

Client
......

.. automodule:: websockets.client

   .. autofunction:: connect(uri)

See also the :ref:`example <client-example>` above.

Utilities
.........

.. automodule:: websockets.http
   :members:

Limitations
-----------

The following parts of RFC 6455 aren't implemented:

- `Subprotocols`_
- `Extensions`_
- `Status codes`_

.. _Subprotocols: http://tools.ietf.org/html/rfc6455#section-1.9
.. _Extensions: http://tools.ietf.org/html/rfc6455#section-9
.. _Status codes: http://tools.ietf.org/html/rfc6455#section-7.4
