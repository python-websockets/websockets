Features
========

.. currentmodule:: websockets

Feature support matrices summarize which implementations support which features.

.. raw:: html

    <style>
        .support-matrix-table { width: 100%; }
        .support-matrix-table th:first-child { text-align: left; }
        .support-matrix-table th:not(:first-child) { text-align: center; width: 15%; }
        .support-matrix-table td:not(:first-child) { text-align: center; }
    </style>

.. |aio| replace:: :mod:`asyncio` (new)
.. |sync| replace:: :mod:`threading`
.. |sans| replace:: `Sans-I/O`_
.. |leg| replace:: :mod:`asyncio` (legacy)
.. _Sans-I/O: https://sans-io.readthedocs.io/

Both sides
----------

.. table::
    :class: support-matrix-table

    +------------------------------------+--------+--------+--------+--------+
    |                                    | |aio|  | |sync| | |sans| | |leg|  |
    +====================================+========+========+========+========+
    | Perform the opening handshake      | ✅     | ✅     | ✅     | ✅     |
    +------------------------------------+--------+--------+--------+--------+
    | Enforce opening timeout            | ✅     | ✅     | —      | ✅     |
    +------------------------------------+--------+--------+--------+--------+
    | Send a message                     | ✅     | ✅     | ✅     | ✅     |
    +------------------------------------+--------+--------+--------+--------+
    | Broadcast a message                | ✅     | ❌     | —      | ✅     |
    +------------------------------------+--------+--------+--------+--------+
    | Receive a message                  | ✅     | ✅     | ✅     | ✅     |
    +------------------------------------+--------+--------+--------+--------+
    | Iterate over received messages     | ✅     | ✅     | —      | ✅     |
    +------------------------------------+--------+--------+--------+--------+
    | Send a fragmented message          | ✅     | ✅     | ✅     | ✅     |
    +------------------------------------+--------+--------+--------+--------+
    | Receive a fragmented message frame | ✅     | ✅     | ✅     | ❌     |
    | by frame                           |        |        |        |        |
    +------------------------------------+--------+--------+--------+--------+
    | Receive a fragmented message after | ✅     | ✅     | —      | ✅     |
    | reassembly                         |        |        |        |        |
    +------------------------------------+--------+--------+--------+--------+
    | Send a ping                        | ✅     | ✅     | ✅     | ✅     |
    +------------------------------------+--------+--------+--------+--------+
    | Respond to pings automatically     | ✅     | ✅     | ✅     | ✅     |
    +------------------------------------+--------+--------+--------+--------+
    | Send a pong                        | ✅     | ✅     | ✅     | ✅     |
    +------------------------------------+--------+--------+--------+--------+
    | Keepalive                          | ✅     | ❌     | —      | ✅     |
    +------------------------------------+--------+--------+--------+--------+
    | Heartbeat                          | ✅     | ❌     | —      | ✅     |
    +------------------------------------+--------+--------+--------+--------+
    | Measure latency                    | ✅     | ❌     | —      | ✅     |
    +------------------------------------+--------+--------+--------+--------+
    | Perform the closing handshake      | ✅     | ✅     | ✅     | ✅     |
    +------------------------------------+--------+--------+--------+--------+
    | Enforce closing timeout            | ✅     | ✅     | —      | ✅     |
    +------------------------------------+--------+--------+--------+--------+
    | Report close codes and reasons     | ✅     | ✅     | ✅     | ❌     |
    | from both sides                    |        |        |        |        |
    +------------------------------------+--------+--------+--------+--------+
    | Compress messages (:rfc:`7692`)    | ✅     | ✅     | ✅     | ✅     |
    +------------------------------------+--------+--------+--------+--------+
    | Tune memory usage for compression  | ✅     | ✅     | ✅     | ✅     |
    +------------------------------------+--------+--------+--------+--------+
    | Negotiate extensions               | ✅     | ✅     | ✅     | ✅     |
    +------------------------------------+--------+--------+--------+--------+
    | Implement custom extensions        | ✅     | ✅     | ✅     | ✅     |
    +------------------------------------+--------+--------+--------+--------+
    | Negotiate a subprotocol            | ✅     | ✅     | ✅     | ✅     |
    +------------------------------------+--------+--------+--------+--------+
    | Enforce security limits            | ✅     | ✅     | ✅     | ✅     |
    +------------------------------------+--------+--------+--------+--------+
    | Log events                         | ✅     | ✅     | ✅     | ✅     |
    +------------------------------------+--------+--------+--------+--------+

Server
------

.. table::
    :class: support-matrix-table

    +------------------------------------+--------+--------+--------+--------+
    |                                    | |aio|  | |sync| | |sans| | |leg|  |
    +====================================+========+========+========+========+
    | Listen on a TCP socket             | ✅     | ✅     | —      | ✅     |
    +------------------------------------+--------+--------+--------+--------+
    | Listen on a Unix socket            | ✅     | ✅     | —      | ✅     |
    +------------------------------------+--------+--------+--------+--------+
    | Listen using a preexisting socket  | ✅     | ✅     | —      | ✅     |
    +------------------------------------+--------+--------+--------+--------+
    | Encrypt connection with TLS        | ✅     | ✅     | —      | ✅     |
    +------------------------------------+--------+--------+--------+--------+
    | Close server on context exit       | ✅     | ✅     | —      | ✅     |
    +------------------------------------+--------+--------+--------+--------+
    | Close connection on handler exit   | ✅     | ✅     | —      | ✅     |
    +------------------------------------+--------+--------+--------+--------+
    | Shut down server gracefully        | ✅     | ✅     | —      | ✅     |
    +------------------------------------+--------+--------+--------+--------+
    | Check ``Origin`` header            | ✅     | ✅     | ✅     | ✅     |
    +------------------------------------+--------+--------+--------+--------+
    | Customize subprotocol selection    | ✅     | ✅     | ✅     | ✅     |
    +------------------------------------+--------+--------+--------+--------+
    | Configure ``Server`` header        | ✅     | ✅     | ✅     | ✅     |
    +------------------------------------+--------+--------+--------+--------+
    | Alter opening handshake request    | ✅     | ✅     | ✅     | ❌     |
    +------------------------------------+--------+--------+--------+--------+
    | Alter opening handshake response   | ✅     | ✅     | ✅     | ❌     |
    +------------------------------------+--------+--------+--------+--------+
    | Force an HTTP response             | ✅     | ✅     | ✅     | ✅     |
    +------------------------------------+--------+--------+--------+--------+
    | Perform HTTP Basic Authentication  | ✅     | ✅     | ❌     | ✅     |
    +------------------------------------+--------+--------+--------+--------+
    | Perform HTTP Digest Authentication | ❌     | ❌     | ❌     | ❌     |
    +------------------------------------+--------+--------+--------+--------+

Client
------

.. table::
    :class: support-matrix-table

    +------------------------------------+--------+--------+--------+--------+
    |                                    | |aio|  | |sync| | |sans| | |leg|  |
    +====================================+========+========+========+========+
    | Connect to a TCP socket            | ✅     | ✅     | —      | ✅     |
    +------------------------------------+--------+--------+--------+--------+
    | Connect to a Unix socket           | ✅     | ✅     | —      | ✅     |
    +------------------------------------+--------+--------+--------+--------+
    | Connect using a preexisting socket | ✅     | ✅     | —      | ✅     |
    +------------------------------------+--------+--------+--------+--------+
    | Encrypt connection with TLS        | ✅     | ✅     | —      | ✅     |
    +------------------------------------+--------+--------+--------+--------+
    | Close connection on context exit   | ✅     | ✅     | —      | ✅     |
    +------------------------------------+--------+--------+--------+--------+
    | Reconnect automatically            | ✅     | ❌     | —      | ✅     |
    +------------------------------------+--------+--------+--------+--------+
    | Configure ``Origin`` header        | ✅     | ✅     | ✅     | ✅     |
    +------------------------------------+--------+--------+--------+--------+
    | Configure ``User-Agent`` header    | ✅     | ✅     | ✅     | ✅     |
    +------------------------------------+--------+--------+--------+--------+
    | Modify opening handshake request   | ✅     | ✅     | ✅     | ✅     |
    +------------------------------------+--------+--------+--------+--------+
    | Modify opening handshake response  | ✅     | ✅     | ✅     | ❌     |
    +------------------------------------+--------+--------+--------+--------+
    | Connect to non-ASCII IRIs          | ✅     | ✅     | ✅     | ✅     |
    +------------------------------------+--------+--------+--------+--------+
    | Follow HTTP redirects              | ✅     | ❌     | —      | ✅     |
    +------------------------------------+--------+--------+--------+--------+
    | Perform HTTP Basic Authentication  | ✅     | ✅     | ✅     | ✅     |
    +------------------------------------+--------+--------+--------+--------+
    | Perform HTTP Digest Authentication | ❌     | ❌     | ❌     | ❌     |
    | (`#784`_)                          |        |        |        |        |
    +------------------------------------+--------+--------+--------+--------+
    | Connect via HTTP proxy (`#364`_)   | ❌     | ❌     | —      | ❌     |
    +------------------------------------+--------+--------+--------+--------+
    | Connect via SOCKS5 proxy (`#475`_) | ❌     | ❌     | —      | ❌     |
    +------------------------------------+--------+--------+--------+--------+

.. _#364: https://github.com/python-websockets/websockets/issues/364
.. _#475: https://github.com/python-websockets/websockets/issues/475
.. _#784: https://github.com/python-websockets/websockets/issues/784

Known limitations
-----------------

There is no way to control compression of outgoing frames on a per-frame basis
(`#538`_). If compression is enabled, all frames are compressed.

.. _#538: https://github.com/python-websockets/websockets/issues/538

The server doesn't check the Host header and doesn't respond with HTTP 400 Bad
Request if it is missing or invalid (`#1246`).

.. _#1246: https://github.com/python-websockets/websockets/issues/1246

The client API doesn't attempt to guarantee that there is no more than one
connection to a given IP address in a CONNECTING state. This behavior is
mandated by :rfc:`6455`, section 4.1. However, :func:`~asyncio.client.connect()`
isn't the right layer for enforcing this constraint. It's the caller's
responsibility.
