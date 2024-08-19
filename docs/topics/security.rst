Security
========

.. currentmodule:: websockets

Encryption
----------

For production use, a server should require encrypted connections.

See this example of :ref:`encrypting connections with TLS
<secure-server-example>`.

Memory usage
------------

.. warning::

    An attacker who can open an arbitrary number of connections will be able
    to perform a denial of service by memory exhaustion. If you're concerned
    by denial of service attacks, you must reject suspicious connections
    before they reach websockets, typically in a reverse proxy.

With the default settings, opening a connection uses 70 KiB of memory.

Sending some highly compressed messages could use up to 128 MiB of memory with
an amplification factor of 1000 between network traffic and memory usage.

Configuring a server to :doc:`optimize memory usage <memory>` will improve
security in addition to improving performance.

HTTP limits
-----------

In the opening handshake, websockets applies limits to the amount of data that
it accepts in order to minimize exposure to denial of service attacks.

The request or status line is limited to 8192 bytes. Each header line, including
the name and value, is limited to 8192 bytes too. No more than 128 HTTP headers
are allowed. When the HTTP response includes a body, it is limited to 1 MiB.

You may change these limits by setting the :envvar:`WEBSOCKETS_MAX_LINE_LENGTH`,
:envvar:`WEBSOCKETS_MAX_NUM_HEADERS`, and :envvar:`WEBSOCKETS_MAX_BODY_SIZE`
environment variables respectively.

Identification
--------------

By default, websockets identifies itself with a ``Server`` or ``User-Agent``
header in the format ``"Python/x.y.z websockets/X.Y"``.

You can set the ``server_header`` argument of :func:`~asyncio.server.serve` or
the ``user_agent_header`` argument of :func:`~asyncio.client.connect` to
configure another value. Setting them to :obj:`None` removes the header.

Alternatively, you can set the :envvar:`WEBSOCKETS_SERVER` and
:envvar:`WEBSOCKETS_USER_AGENT` environment variables respectively. Setting them
to an empty string removes the header.

If both the argument and the environment variable are set, the argument takes
precedence.
