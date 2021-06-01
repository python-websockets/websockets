Client
======

.. automodule:: websockets.client

    Opening a connection
    --------------------

    .. autofunction:: connect(uri, *, create_protocol=None, ping_interval=20, ping_timeout=20, close_timeout=10, max_size=2 ** 20, max_queue=2 ** 5, read_limit=2 ** 16, write_limit=2 ** 16, compression='deflate', origin=None, extensions=None, subprotocols=None, extra_headers=None, logger=None, **kwds)
        :async:

    .. autofunction:: unix_connect(path, uri="ws://localhost/", *, create_protocol=None, ping_interval=20, ping_timeout=20, close_timeout=10, max_size=2 ** 20, max_queue=2 ** 5, read_limit=2 ** 16, write_limit=2 ** 16, compression='deflate', origin=None, extensions=None, subprotocols=None, extra_headers=None, logger=None, **kwds)
        :async:

    Using a connection
    ------------------

    .. autoclass:: WebSocketClientProtocol(*, ping_interval=20, ping_timeout=20, close_timeout=10, max_size=2 ** 20, max_queue=2 ** 5, read_limit=2 ** 16, write_limit=2 ** 16, origin=None, extensions=None, subprotocols=None, extra_headers=None, logger=None)

        .. attribute:: id

            UUID for the connection.

            Useful for identifying connections in logs.

        .. autoattribute:: local_address

        .. autoattribute:: remote_address

        .. autoattribute:: open

        .. autoattribute:: closed

        .. attribute:: path

            Path of the HTTP request.

            Available once the connection is open.

        .. attribute:: request_headers

            HTTP request headers as a :class:`~websockets.http.Headers` instance.

            Available once the connection is open.

        .. attribute:: response_headers

            HTTP response headers as a :class:`~websockets.http.Headers` instance.

            Available once the connection is open.

        .. attribute:: subprotocol

            Subprotocol, if one was negotiated.

            Available once the connection is open.

        .. attribute:: close_code

            WebSocket close code.

            Available once the connection is closed.

        .. attribute:: close_reason

            WebSocket close reason.

            Available once the connection is closed.

        .. automethod:: recv

        .. automethod:: send

        .. automethod:: ping

        .. automethod:: pong

        .. automethod:: close

        .. automethod:: wait_closed
