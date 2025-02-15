Proxies
=======

.. currentmodule:: websockets

If a proxy is configured in the operating system or with an environment
variable, websockets uses it automatically when connecting to a server.

Configuration
-------------

First, if the server is in the proxy bypass list of the operating system or in
the ``no_proxy`` environment variable, websockets connects directly.

Then, it looks for a proxy in the following locations:

1. The ``wss_proxy`` or ``ws_proxy`` environment variables for ``wss://`` and
   ``ws://`` connections respectively. They allow configuring a specific proxy
   for WebSocket connections.
2. A SOCKS proxy configured in the operating system.
3. An HTTP proxy configured in the operating system or in the ``https_proxy``
   environment variable, for both ``wss://`` and ``ws://`` connections.
4. An HTTP proxy configured in the operating system or in the ``http_proxy``
   environment variable, only for ``ws://`` connections.

Finally, if no proxy is found, websockets connects directly.

While environment variables are case-insensitive, the lower-case spelling is the
most common, for `historical reasons`_, and recommended.

.. _historical reasons: https://unix.stackexchange.com/questions/212894/

websockets authenticates automatically when the address of the proxy includes
credentials e.g. ``http://user:password@proxy:8080/``.

.. admonition:: Any environment variable can configure a SOCKS proxy or an HTTP proxy.
    :class: tip

    For example, ``https_proxy=socks5h://proxy:1080/`` configures a SOCKS proxy
    for all WebSocket connections. Likewise, ``wss_proxy=http://proxy:8080/``
    configures an HTTP proxy only for ``wss://`` connections.

.. admonition:: What if websockets doesn't select the right proxy?
    :class: hint

    websockets relies on :func:`~urllib.request.getproxies()` to read the proxy
    configuration. Check that it returns what you expect. If it doesn't, review
    your proxy configuration.

You can override the default configuration and configure a proxy explicitly with
the ``proxy`` argument of :func:`~asyncio.client.connect`. Set ``proxy=None`` to
disable the proxy.

SOCKS proxies
-------------

Connecting through a SOCKS proxy requires installing the third-party library
`python-socks`_:

.. code-block:: console

    $ pip install python-socks\[asyncio\]

.. _python-socks: https://github.com/romis2012/python-socks

python-socks supports SOCKS4, SOCKS4a, SOCKS5, and SOCKS5h. The protocol version
is configured in the address of the proxy e.g. ``socks5h://proxy:1080/``. When a
SOCKS proxy is configured in the operating system, python-socks uses SOCKS5h.

python-socks supports username/password authentication for SOCKS5 (:rfc:`1929`)
but does not support other authentication methods such as GSSAPI (:rfc:`1961`).

HTTP proxies
------------

When the address of the proxy starts with ``https://``, websockets secures the
connection to the proxy with TLS.

When the address of the server starts with ``wss://``, websockets secures the
connection from the proxy to the server with TLS.

These two options are compatible. TLS-in-TLS is supported.

The documentation of :func:`~asyncio.client.connect` describes how to configure
TLS from websockets to the proxy and from the proxy to the server.

websockets supports proxy authentication with Basic Auth.
