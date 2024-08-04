import logging
import os


format = "%(asctime)s %(levelname)s %(name)s %(message)s"

if bool(os.environ.get("WEBSOCKETS_DEBUG")):  # pragma: no cover
    # Display every frame sent or received in debug mode.
    level = logging.DEBUG
else:
    # Hide stack traces of exceptions.
    level = logging.CRITICAL

logging.basicConfig(format=format, level=level)
