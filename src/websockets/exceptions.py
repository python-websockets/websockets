import http
from typing import Optional

from .http import Headers, HeadersLike


__all__ = [
    "AbortHandshake",
    "ConnectionClosed",
    "ConnectionClosedError",
    "ConnectionClosedOK",
    "DuplicateParameter",
    "InvalidHandshake",
    "InvalidHeader",
    "InvalidHeaderFormat",
    "InvalidHeaderValue",
    "InvalidMessage",
    "InvalidOrigin",
    "InvalidParameterName",
    "InvalidParameterValue",
    "InvalidState",
    "InvalidStatusCode",
    "InvalidUpgrade",
    "InvalidURI",
    "NegotiationError",
    "PayloadTooBig",
    "WebSocketProtocolError",
]


class InvalidHandshake(Exception):
    """
    Exception raised when a handshake request or response is invalid.

    """


class AbortHandshake(InvalidHandshake):
    """
    Exception raised to abort a handshake and return a HTTP response.

    """

    def __init__(
        self, status: http.HTTPStatus, headers: HeadersLike, body: bytes = b""
    ) -> None:
        self.status = status
        self.headers = Headers(headers)
        self.body = body
        message = f"HTTP {status}, {len(self.headers)} headers, {len(body)} bytes"
        super().__init__(message)


class RedirectHandshake(InvalidHandshake):
    """
    Exception raised when a handshake gets redirected.

    """

    def __init__(self, uri: str) -> None:
        self.uri = uri


class InvalidMessage(InvalidHandshake):
    """
    Exception raised when the HTTP message in a handshake request is malformed.

    """


class InvalidHeader(InvalidHandshake):
    """
    Exception raised when a HTTP header doesn't have a valid format or value.

    """

    def __init__(self, name: str, value: Optional[str] = None) -> None:
        if value is None:
            message = f"Missing {name} header"
        elif value == "":
            message = f"Empty {name} header"
        else:
            message = f"Invalid {name} header: {value}"
        super().__init__(message)


class InvalidHeaderFormat(InvalidHeader):
    """
    Exception raised when a Sec-WebSocket-* HTTP header cannot be parsed.

    """

    def __init__(self, name: str, error: str, header: str, pos: int) -> None:
        error = f"{error} at {pos} in {header}"
        super().__init__(name, error)


class InvalidHeaderValue(InvalidHeader):
    """
    Exception raised when a Sec-WebSocket-* HTTP header has a wrong value.

    """


class InvalidUpgrade(InvalidHeader):
    """
    Exception raised when a Upgrade or Connection header isn't correct.

    """


class InvalidOrigin(InvalidHeader):
    """
    Exception raised when the Origin header in a request isn't allowed.

    """

    def __init__(self, origin: Optional[str]) -> None:
        super().__init__("Origin", origin)


class InvalidStatusCode(InvalidHandshake):
    """
    Exception raised when a handshake response status code is invalid.

    Provides the integer status code in its ``status_code`` attribute.

    """

    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        message = f"Status code not 101: {status_code}"
        super().__init__(message)


class NegotiationError(InvalidHandshake):
    """
    Exception raised when negotiating an extension fails.

    """


class InvalidParameterName(NegotiationError):
    """
    Exception raised when a parameter name in an extension header is invalid.

    """

    def __init__(self, name: str) -> None:
        self.name = name
        message = f"Invalid parameter name: {name}"
        super().__init__(message)


class InvalidParameterValue(NegotiationError):
    """
    Exception raised when a parameter value in an extension header is invalid.

    """

    def __init__(self, name: str, value: Optional[str]) -> None:
        self.name = name
        self.value = value
        message = f"Invalid value for parameter {name}: {value}"
        super().__init__(message)


class DuplicateParameter(NegotiationError):
    """
    Exception raised when a parameter name is repeated in an extension header.

    """

    def __init__(self, name: str) -> None:
        self.name = name
        message = f"Duplicate parameter: {name}"
        super().__init__(message)


class InvalidState(Exception):
    """
    Exception raised when an operation is forbidden in the current state.

    """


CLOSE_CODES = {
    1000: "OK",
    1001: "going away",
    1002: "protocol error",
    1003: "unsupported type",
    # 1004 is reserved
    1005: "no status code [internal]",
    1006: "connection closed abnormally [internal]",
    1007: "invalid data",
    1008: "policy violation",
    1009: "message too big",
    1010: "extension required",
    1011: "unexpected error",
    1015: "TLS failure [internal]",
}


def format_close(code: int, reason: str) -> str:
    """
    Display a human-readable version of the close code and reason.

    """
    if 3000 <= code < 4000:
        explanation = "registered"
    elif 4000 <= code < 5000:
        explanation = "private use"
    else:
        explanation = CLOSE_CODES.get(code, "unknown")
    result = f"code = {code} ({explanation}), "

    if reason:
        result += f"reason = {reason}"
    else:
        result += "no reason"

    return result


class ConnectionClosed(InvalidState):
    """
    Exception raised when trying to read or write on a closed connection.

    Provides the connection close code and reason in its ``code`` and
    ``reason`` attributes respectively.

    """

    def __init__(self, code: int, reason: str) -> None:
        self.code = code
        self.reason = reason
        message = "WebSocket connection is closed: "
        message += format_close(code, reason)
        super().__init__(message)


class ConnectionClosedError(ConnectionClosed):
    """
    Like :exc:`ConnectionClosed`, when the connection terminated with an error.

    This means the close code is different from 1000 (OK) and 1001 (going away).

    """

    def __init__(self, code: int, reason: str) -> None:
        assert code != 1000 and code != 1001
        super().__init__(code, reason)


class ConnectionClosedOK(ConnectionClosed):
    """
    Like :exc:`ConnectionClosed`, when the connection terminated properly.

    This means the close code is 1000 (OK) or 1001 (going away).

    """

    def __init__(self, code: int, reason: str) -> None:
        assert code == 1000 or code == 1001
        super().__init__(code, reason)


class InvalidURI(Exception):
    """
    Exception raised when an URI isn't a valid websocket URI.

    """

    def __init__(self, uri: str) -> None:
        self.uri = uri
        message = "{} isn't a valid URI".format(uri)
        super().__init__(message)


class PayloadTooBig(Exception):
    """
    Exception raised when a frame's payload exceeds the maximum size.

    """


class WebSocketProtocolError(Exception):
    """
    Internal exception raised when the remote side breaks the protocol.

    """
