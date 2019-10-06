import asyncio
import sys
import warnings
from typing import Tuple

# For backwards compatibility:
# Headers and MultipleValuesError used to be defined in this module
from .datastructures import Headers, MultipleValuesError  # noqa
from .version import version as websockets_version


__all__ = ["USER_AGENT"]


PYTHON_VERSION = "{}.{}".format(*sys.version_info)
USER_AGENT = f"Python/{PYTHON_VERSION} websockets/{websockets_version}"


# Backwards compatibility with previously documented public APIs


async def read_request(
    stream: asyncio.StreamReader,
) -> Tuple[str, Headers]:  # pragma: no cover
    warnings.warn("websockets.http.read_request is deprecated", DeprecationWarning)
    from .http_legacy import read_request

    return await read_request(stream)


async def read_response(
    stream: asyncio.StreamReader,
) -> Tuple[int, str, Headers]:  # pragma: no cover
    warnings.warn("websockets.http.read_response is deprecated", DeprecationWarning)
    from .http_legacy import read_response

    return await read_response(stream)
