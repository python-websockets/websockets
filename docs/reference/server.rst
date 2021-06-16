Server
======

.. automodule:: websockets.server

    Starting a server
    -----------------

    .. autofunction:: serve(ws_handler, host=None, port=None, *, create_protocol=None, ping_interval=20, ping_timeout=20, close_timeout=10, max_size=2 ** 20, max_queue=2 ** 5, read_limit=2 ** 16, write_limit=2 ** 16, compression='deflate', origins=None, extensions=None, subprotocols=None, extra_headers=None, process_request=None, select_subprotocol=None, logger=None, **kwds)
        :async:

    .. autofunction:: unix_serve(ws_handler, path, *, create_protocol=None, ping_interval=20, ping_timeout=20, close_timeout=10, max_size=2 ** 20, max_queue=2 ** 5, read_limit=2 ** 16, write_limit=2 ** 16, compression='deflate', origins=None, extensions=None, subprotocols=None, extra_headers=None, process_request=None, select_subprotocol=None, logger=None, **kwds)
        :async:

    Stopping a server
    -----------------

    .. autoclass:: WebSocketServer

        .. autoattribute:: sockets

        .. automethod:: close
        .. automethod:: wait_closed

    Using a connection
    ------------------

    .. autoclass:: WebSocketServerProtocol(ws_handler, ws_server, *, ping_interval=20, ping_timeout=20, close_timeout=10, max_size=2 ** 20, max_queue=2 ** 5, read_limit=2 ** 16, write_limit=2 ** 16, origins=None, extensions=None, subprotocols=None, extra_headers=None, process_request=None, select_subprotocol=None, logger=None)

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

        .. autoattribute:: close_code

        .. autoattribute:: close_reason

        .. automethod:: process_request

        .. automethod:: select_subprotocol

        .. automethod:: recv

        .. automethod:: send

        .. automethod:: ping

        .. automethod:: pong

        .. automethod:: close

        .. automethod:: wait_closed

Basic authentication
--------------------

.. automodule:: websockets.auth

    .. autofunction:: basic_auth_protocol_factory

    .. autoclass:: BasicAuthWebSocketServerProtocol

        .. attribute:: realm

            Scope of protection.

            If provided, it should contain only ASCII characters because the
            encoding of non-ASCII characters is undefined.

        .. attribute:: username

            Username of the authenticated user.

        .. automethod:: check_credentials
