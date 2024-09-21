from __future__ import annotations

import warnings

from .legacy.auth import *
from .legacy.auth import __all__  # noqa: F401


warnings.warn(  # deprecated in 14.0
    "websockets.auth is deprecated",
    DeprecationWarning,
)
