from __future__ import annotations

import sys


__all__ = ["asyncio_timeout", "asyncio_timeout_at"]


if sys.version_info[:2] >= (3, 11):
    from asyncio import (
        timeout as asyncio_timeout,  # noqa: F401
        timeout_at as asyncio_timeout_at,  # noqa: F401
    )
else:
    from .async_timeout import (
        timeout as asyncio_timeout,  # noqa: F401
        timeout_at as asyncio_timeout_at,  # noqa: F401
    )
