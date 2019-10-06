import warnings

from .datastructures import Headers


__all__ = ["build_request", "check_request", "build_response", "check_response"]


GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


# Backwards compatibility with previously documented public APIs


def build_request(headers: Headers) -> str:  # pragma: no cover
    warnings.warn(
        "websockets.handshake.build_request is deprecated", DeprecationWarning
    )
    from .handshake_legacy import build_request

    return build_request(headers)


def check_request(headers: Headers) -> str:  # pragma: no cover
    warnings.warn(
        "websockets.handshake.check_request is deprecated", DeprecationWarning
    )
    from .handshake_legacy import check_request

    return check_request(headers)


def build_response(headers: Headers, key: str) -> None:  # pragma: no cover
    warnings.warn(
        "websockets.handshake.build_response is deprecated", DeprecationWarning
    )
    from .handshake_legacy import build_response

    return build_response(headers, key)


def check_response(headers: Headers, key: str) -> None:  # pragma: no cover
    warnings.warn(
        "websockets.handshake.check_response is deprecated", DeprecationWarning
    )
    from .handshake_legacy import check_response

    return check_response(headers, key)
