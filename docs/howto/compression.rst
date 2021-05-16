Compression
===========

:func:`~websockets.client.connect` and :func:`~websockets.server.serve` enable
compression by default.

If you want to disable it, set ``compression=None``::

    import websockets

    websockets.connect(..., compression=None)

    websockets.serve(..., compression=None)

.. _per-message-deflate-configuration-example:

You can also configure the Per-Message Deflate extension explicitly if you
want to customize compression settings::

    import websockets
    from websockets.extensions import permessage_deflate

    websockets.connect(
        ...,
        extensions=[
            permessage_deflate.ClientPerMessageDeflateFactory(
                server_max_window_bits=11,
                client_max_window_bits=11,
                compress_settings={'memLevel': 4},
            ),
        ],
    )

    websockets.serve(
        ...,
        extensions=[
            permessage_deflate.ServerPerMessageDeflateFactory(
                server_max_window_bits=11,
                client_max_window_bits=11,
                compress_settings={'memLevel': 4},
            ),
        ],
    )

The window bits and memory level values chosen in these examples reduce memory
usage. You can read more about :ref:`optimizing compression settings
<compression-settings>`.

Refer to the API documentation of
:class:`~permessage_deflate.ClientPerMessageDeflateFactory` and
:class:`~permessage_deflate.ServerPerMessageDeflateFactory` for details.
