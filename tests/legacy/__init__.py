from __future__ import annotations

import warnings


with warnings.catch_warnings():
    # Suppress DeprecationWarning raised by websockets.legacy.
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    import websockets.legacy  # noqa: F401
