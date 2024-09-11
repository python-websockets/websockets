Environment variables
=====================

.. currentmodule:: websockets

Logging
-------

.. envvar:: WEBSOCKETS_MAX_LOG_SIZE

    How much of each frame to show in debug logs.

    The default value is ``75``.

See the :doc:`logging guide <../topics/logging>` for details.

Security
--------

.. envvar:: WEBSOCKETS_SERVER

    Server header sent by websockets.

    The default value uses the format ``"Python/x.y.z websockets/X.Y"``.

.. envvar:: WEBSOCKETS_USER_AGENT

    User-Agent header sent by websockets.

    The default value uses the format ``"Python/x.y.z websockets/X.Y"``.

.. envvar:: WEBSOCKETS_MAX_LINE_LENGTH

    Maximum length of the request or status line in the opening handshake.

    The default value is ``8192`` bytes.

.. envvar:: WEBSOCKETS_MAX_NUM_HEADERS

    Maximum number of HTTP headers in the opening handshake.

    The default value is ``128`` bytes.

.. envvar:: WEBSOCKETS_MAX_BODY_SIZE

    Maximum size of the body of an HTTP response in the opening handshake.

    The default value is ``1_048_576`` bytes (1 MiB).

See the :doc:`security guide <../topics/security>` for details.

Reconnection
------------

Reconnection attempts are spaced out with truncated exponential backoff.

.. envvar:: BACKOFF_INITIAL_DELAY

    The first attempt is delayed by a random amount of time between ``0`` and
    ``BACKOFF_INITIAL_DELAY`` seconds.

    The default value is ``5.0`` seconds.

.. envvar:: BACKOFF_MIN_DELAY

    The second attempt is delayed by ``BACKOFF_MIN_DELAY`` seconds.

    The default value is ``3.1`` seconds.

.. envvar:: BACKOFF_FACTOR

    After the second attempt, the delay is multiplied by ``BACKOFF_FACTOR``
    between each attempt.

    The default value is ``1.618``.

.. envvar:: BACKOFF_MAX_DELAY

    The delay between attempts is capped at ``BACKOFF_MAX_DELAY`` seconds.

    The default value is ``90.0`` seconds.

Redirects
---------

.. envvar:: WEBSOCKETS_MAX_REDIRECTS

    Maximum number of redirects that :func:`~asyncio.client.connect` follows.

    The default value is ``10``.
