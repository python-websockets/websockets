Enable debug logs
==================

websockets logs events with the :mod:`logging` module from the standard library.

It writes to the ``"websockets.server"`` and ``"websockets.client"`` loggers.

Enable logs at the ``DEBUG`` level to see exactly what websockets is doing.

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

Refer to the :doc:`logging guide <../topics/logging>` for more details on
logging in websockets.

In addition, you may enable asyncio's `debug mode`_ to see what asyncio is
doing.

.. _debug mode: https://docs.python.org/3/library/asyncio-dev.html#asyncio-debug-mode
