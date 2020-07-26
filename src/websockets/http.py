import asyncio
import ipaddress
import sys
import warnings
from typing import Tuple

# For backwards compatibility:
# Headers and MultipleValuesError used to be defined in this module
from .datastructures import Headers, MultipleValuesError  # noqa
from .version import version as websockets_version


__all__ = ["USER_AGENT", "build_host"]


PYTHON_VERSION = "{}.{}".format(*sys.version_info)
USER_AGENT = f"Python/{PYTHON_VERSION} websockets/{websockets_version}"


def build_host(host: str, port: int, secure: bool) -> str:
    """
    Build a ``Host`` header.

    """
    # https://tools.ietf.org/html/rfc3986#section-3.2.2
    # IPv6 addresses must be enclosed in brackets.
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        # host is a hostname
        pass
    else:
        # host is an IP address
        if address.version == 6:
            host = f"[{host}]"

    if port != (443 if secure else 80):
        host = f"{host}:{port}"

    return host


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
