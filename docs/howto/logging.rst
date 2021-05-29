Configure logging
=================

Disable logging
---------------

If your application doesn't configure :mod:`logging`, Python outputs messages
of severity :data:`~logging.WARNING` and higher to :data:`~sys.stderr`. If
you want to disable this behavior for websockets, you can add
a :class:`~logging.NullHandler`::

    logging.getLogger("websockets").addHandler(logging.NullHandler())

Additionally, if your application configures :mod:`logging`, you must disable
propagation to the root logger, or else its handlers could output logs::

    logging.getLogger("websockets").propagate = False

Alternatively, you could set the log level to :data:`~logging.CRITICAL` for
websockets, as the highest level currently used is :data:`~logging.ERROR`::

    logging.getLogger("websockets").setLevel(logging.CRITICAL)

Or you could configure a filter to drop all messages::

    logging.getLogger("websockets").addFilter(lambda record: None)
