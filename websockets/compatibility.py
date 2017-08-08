import asyncio
import http


# Replace with BaseEventLoop.create_task when dropping Python < 3.4.2.
try:                                                # pragma: no cover
    asyncio_ensure_future = asyncio.ensure_future   # Python ≥ 3.5
except AttributeError:                              # pragma: no cover
    asyncio_ensure_future = asyncio.async           # Python < 3.5

try:                                                # pragma: no cover
                                                    # Python ≥ 3.5
    SWITCHING_PROTOCOLS = http.HTTPStatus.SWITCHING_PROTOCOLS
    # Used only in tests.
    UNAUTHORIZED = http.HTTPStatus.UNAUTHORIZED
    FORBIDDEN = http.HTTPStatus.FORBIDDEN
except AttributeError:                              # pragma: no cover
                                                    # Python < 3.5
    class SWITCHING_PROTOCOLS:
        value = 101
        phrase = "Switching Protocols"

    class UNAUTHORIZED:
        value = 401
        phrase = "Unauthorized"

    class FORBIDDEN:
        value = 403
        phrase = "Forbidden"
