import logging
import os
import platform


if platform.python_implementation() != "PyPy":  # pragma: no branch
    import tracemalloc


format = "%(asctime)s %(levelname)s %(name)s %(message)s"

if bool(os.environ.get("WEBSOCKETS_DEBUG")):  # pragma: no cover
    # Display every frame sent or received in debug mode.
    level = logging.DEBUG
else:
    # Hide stack traces of exceptions.
    level = logging.CRITICAL

logging.basicConfig(format=format, level=level)

if bool(os.environ.get("WEBSOCKETS_TRACE")):  # pragma: no cover
    # Trace allocations to debug resource warnings.
    tracemalloc.start()
