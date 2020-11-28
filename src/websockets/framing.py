import warnings

from .legacy.framing import *  # noqa


warnings.warn("websockets.framing is deprecated", DeprecationWarning)
