Encrypt connections
====================

.. currentmodule:: websockets

You should always secure WebSocket connections with TLS_ (Transport Layer
Security).

.. admonition:: TLS vs. SSL
    :class: tip

    TLS is sometimes referred to as SSL (Secure Sockets Layer). SSL was an
    earlier encryption protocol; the name stuck.

The ``wss`` protocol is to ``ws`` what ``https`` is to ``http``.

Secure WebSocket connections require certificates just like HTTPS.

.. _TLS: https://developer.mozilla.org/en-US/docs/Web/Security/Transport_Layer_Security

.. admonition:: Configure the TLS context securely
    :class: attention

    The examples below demonstrate the ``ssl`` argument with a TLS certificate
    shared between the client and the server. This is a simplistic setup.

    Please review the advice and security considerations in the documentation of
    the :mod:`ssl` module to configure the TLS context appropriately.

Servers
-------

In a typical :doc:`deployment <../deploy/index>`, the server is behind a reverse
proxy that terminates TLS. The client connects to the reverse proxy with TLS and
the reverse proxy connects to the server without TLS.

In that case, you don't need to configure TLS in websockets.

If needed in your setup, you can terminate TLS in the server.

In the example below, :func:`~asyncio.server.serve` is configured to receive
secure connections. Before running this server, download
:download:`localhost.pem <../../example/tls/localhost.pem>` and save it in the
same directory as ``server.py``.

.. literalinclude:: ../../example/tls/server.py
    :caption: server.py

Receive both plain and TLS connections on the same port isn't supported.

Clients
-------

:func:`~asyncio.client.connect` enables TLS automatically when connecting to a
``wss://...`` URI.

This works out of the box when the TLS certificate of the server is valid,
meaning it's signed by a certificate authority that your Python installation
trusts.

In the example above, since the server uses a self-signed certificate, the
client needs to be configured to trust the certificate. Here's how to do so.

.. literalinclude:: ../../example/tls/client.py
    :caption: client.py
