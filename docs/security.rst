Security
========

Memory use
----------
.. warning::

    An attacker who can open an arbitrary number of connections will be able
    to perform a denial of service by memory exhaustion. If you're concerned
    by denial of service attacks, you must reject suspicious connections
    before they reach ``websockets``, typically in a reverse proxy.

The baseline memory use for a connection is about 20kB.

The incoming bytes buffer, incoming messages queue and outgoing bytes buffer
contribute to the memory use of a connection. By default, each bytes buffer
takes up to 64kB and the messages queue up to 128MB, which is very large.

Most applications use small messages. Setting ``max_size`` according to the
application's requirements is strongly recommended. See :ref:`buffers` for
details about tuning buffers.

When compression is enabled, additional memory may be allocated for carrying
the compression context across messages, depending on the context takeover and
window size parameters. With the default configuration, this adds 320kB to the
memory use for a connection.

You can reduce this amount by configuring the ``PerMessageDeflate`` extension
with lower ``server_max_window_bits`` and ``client_max_window_bits`` values.
These parameters default is 15. Lowering them to 11 is a good choice.

Finally, memory consumed by your application code also counts towards the
memory use of a connection.

Other limits
------------

``websockets`` implements additional limits on the amount of data it accepts
in order to mimimize exposure to security vulnerabilities.

In the opening handshake, ``websockets`` limits the number of HTTP headers to
256 and the size of an individual header to 4096 bytes. These limits are 10 to
20 times larger than what's expected in standard use cases. They're hardcoded.
If you need to change them, monkey-patch the constants in ``websockets.http``.
