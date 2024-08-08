Environment variables
=====================

Logging
-------

.. envvar:: WEBSOCKETS_MAX_LOG_SIZE

    How much of each frame to show in debug logs.

    The default value is ``75``.

See the :doc:`logging guide <../topics/logging>` for details.

Security
........

.. envvar:: WEBSOCKETS_SERVER

    Server header sent by websockets.

    The default value uses the format ``"Python/x.y.z websockets/X.Y"``.

.. envvar:: WEBSOCKETS_USER_AGENT

    User-Agent header sent by websockets.

    The default value uses the format ``"Python/x.y.z websockets/X.Y"``.

.. envvar:: WEBSOCKETS_MAX_LINE_LENGTH

    Maximum length of the request or status line in the opening handshake.

    The default value is ``8192``.

.. envvar:: WEBSOCKETS_MAX_NUM_HEADERS

    Maximum number of HTTP headers in the opening handshake.

    The default value is ``128``.

.. envvar:: WEBSOCKETS_MAX_BODY_SIZE

    Maximum size of the body of an HTTP response in the opening handshake.

    The default value is ``1_048_576`` (1 MiB).

See the :doc:`security guide <../topics/security>` for details.
