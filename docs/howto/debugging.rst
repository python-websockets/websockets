Enable debug logs
==================

websockets logs events with the :mod:`logging` module from the standard library.

It emits logs in the ``"websockets.server"`` and ``"websockets.client"``
loggers.

You can enable logs at the ``DEBUG`` level to see exactly what websockets does.

If logging isn't configured in your application::

    import logging

    logging.basicConfig(
        format="%(asctime)s %(message)s",
        level=logging.DEBUG,
    )

If logging is already configured::

    import logging

    logger = logging.getLogger("websockets")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(logging.StreamHandler())

Refer to the :doc:`logging guide <../topics/logging>` for more information about
logging in websockets.

You may also enable asyncio's `debug mode`_ to get warnings about classic
pitfalls.

.. _debug mode: https://docs.python.org/3/library/asyncio-dev.html#asyncio-debug-mode
