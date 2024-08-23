"""
:mod:`websockets.exceptions` defines the following exception hierarchy:

* :exc:`WebSocketException`
    * :exc:`ConnectionClosed`
        * :exc:`ConnectionClosedError`
        * :exc:`ConnectionClosedOK`
    * :exc:`InvalidHandshake`
        * :exc:`SecurityError`
        * :exc:`InvalidMessage` (legacy)
        * :exc:`InvalidHeader`
            * :exc:`InvalidHeaderFormat`
            * :exc:`InvalidHeaderValue`
            * :exc:`InvalidOrigin`
            * :exc:`InvalidUpgrade`
        * :exc:`InvalidStatus`
        * :exc:`InvalidStatusCode` (legacy)
        * :exc:`NegotiationError`
            * :exc:`DuplicateParameter`
            * :exc:`InvalidParameterName`
            * :exc:`InvalidParameterValue`
        * :exc:`AbortHandshake` (legacy)
        * :exc:`RedirectHandshake`
    * :exc:`InvalidState`
    * :exc:`InvalidURI`
    * :exc:`PayloadTooBig`
    * :exc:`ProtocolError`

"""

from __future__ import annotations

import typing
import warnings

from . import frames, http11
from .imports import lazy_import


__all__ = [
    "WebSocketException",
    "ConnectionClosed",
    "ConnectionClosedError",
    "ConnectionClosedOK",
    "InvalidHandshake",
    "SecurityError",
    "InvalidMessage",
    "InvalidHeader",
    "InvalidHeaderFormat",
    "InvalidHeaderValue",
    "InvalidOrigin",
    "InvalidUpgrade",
    "InvalidStatus",
    "InvalidStatusCode",
    "NegotiationError",
    "DuplicateParameter",
    "InvalidParameterName",
    "InvalidParameterValue",
    "AbortHandshake",
    "RedirectHandshake",
    "InvalidState",
    "InvalidURI",
    "PayloadTooBig",
    "ProtocolError",
    "WebSocketProtocolError",
]


class WebSocketException(Exception):
    """
    Base class for all exceptions defined by websockets.

    """


class ConnectionClosed(WebSocketException):
    """
    Raised when trying to interact with a closed connection.

    Attributes:
        rcvd: If a close frame was received, its code and reason are available
            in ``rcvd.code`` and ``rcvd.reason``.
        sent: If a close frame was sent, its code and reason are available
            in ``sent.code`` and ``sent.reason``.
        rcvd_then_sent: If close frames were received and sent, this attribute
            tells in which order this happened, from the perspective of this
            side of the connection.

    """

    def __init__(
        self,
        rcvd: frames.Close | None,
        sent: frames.Close | None,
        rcvd_then_sent: bool | None = None,
    ) -> None:
        self.rcvd = rcvd
        self.sent = sent
        self.rcvd_then_sent = rcvd_then_sent
        assert (self.rcvd_then_sent is None) == (self.rcvd is None or self.sent is None)

    def __str__(self) -> str:
        if self.rcvd is None:
            if self.sent is None:
                return "no close frame received or sent"
            else:
                return f"sent {self.sent}; no close frame received"
        else:
            if self.sent is None:
                return f"received {self.rcvd}; no close frame sent"
            else:
                if self.rcvd_then_sent:
                    return f"received {self.rcvd}; then sent {self.sent}"
                else:
                    return f"sent {self.sent}; then received {self.rcvd}"

    # code and reason attributes are provided for backwards-compatibility

    @property
    def code(self) -> int:
        warnings.warn(  # deprecated in 13.1
            "ConnectionClosed.code is deprecated; "
            "use Protocol.close_code or ConnectionClosed.rcvd.code",
            DeprecationWarning,
        )
        if self.rcvd is None:
            return frames.CloseCode.ABNORMAL_CLOSURE
        return self.rcvd.code

    @property
    def reason(self) -> str:
        warnings.warn(  # deprecated in 13.1
            "ConnectionClosed.reason is deprecated; "
            "use Protocol.close_reason or ConnectionClosed.rcvd.reason",
            DeprecationWarning,
        )
        if self.rcvd is None:
            return ""
        return self.rcvd.reason


class ConnectionClosedError(ConnectionClosed):
    """
    Like :exc:`ConnectionClosed`, when the connection terminated with an error.

    A close frame with a code other than 1000 (OK) or 1001 (going away) was
    received or sent, or the closing handshake didn't complete properly.

    """


class ConnectionClosedOK(ConnectionClosed):
    """
    Like :exc:`ConnectionClosed`, when the connection terminated properly.

    A close code with code 1000 (OK) or 1001 (going away) or without a code was
    received and sent.

    """


class InvalidHandshake(WebSocketException):
    """
    Raised during the handshake when the WebSocket connection fails.

    """


class SecurityError(InvalidHandshake):
    """
    Raised when a handshake request or response breaks a security rule.

    Security limits are hard coded.

    """


class InvalidHeader(InvalidHandshake):
    """
    Raised when an HTTP header doesn't have a valid format or value.

    """

    def __init__(self, name: str, value: str | None = None) -> None:
        self.name = name
        self.value = value

    def __str__(self) -> str:
        if self.value is None:
            return f"missing {self.name} header"
        elif self.value == "":
            return f"empty {self.name} header"
        else:
            return f"invalid {self.name} header: {self.value}"


class InvalidHeaderFormat(InvalidHeader):
    """
    Raised when an HTTP header cannot be parsed.

    The format of the header doesn't match the grammar for that header.

    """

    def __init__(self, name: str, error: str, header: str, pos: int) -> None:
        super().__init__(name, f"{error} at {pos} in {header}")


class InvalidHeaderValue(InvalidHeader):
    """
    Raised when an HTTP header has a wrong value.

    The format of the header is correct but a value isn't acceptable.

    """


class InvalidOrigin(InvalidHeader):
    """
    Raised when the Origin header in a request isn't allowed.

    """

    def __init__(self, origin: str | None) -> None:
        super().__init__("Origin", origin)


class InvalidUpgrade(InvalidHeader):
    """
    Raised when the Upgrade or Connection header isn't correct.

    """


class InvalidStatus(InvalidHandshake):
    """
    Raised when a handshake response rejects the WebSocket upgrade.

    """

    def __init__(self, response: http11.Response) -> None:
        self.response = response

    def __str__(self) -> str:
        return (
            "server rejected WebSocket connection: "
            f"HTTP {self.response.status_code:d}"
        )


class NegotiationError(InvalidHandshake):
    """
    Raised when negotiating an extension fails.

    """


class DuplicateParameter(NegotiationError):
    """
    Raised when a parameter name is repeated in an extension header.

    """

    def __init__(self, name: str) -> None:
        self.name = name

    def __str__(self) -> str:
        return f"duplicate parameter: {self.name}"


class InvalidParameterName(NegotiationError):
    """
    Raised when a parameter name in an extension header is invalid.

    """

    def __init__(self, name: str) -> None:
        self.name = name

    def __str__(self) -> str:
        return f"invalid parameter name: {self.name}"


class InvalidParameterValue(NegotiationError):
    """
    Raised when a parameter value in an extension header is invalid.

    """

    def __init__(self, name: str, value: str | None) -> None:
        self.name = name
        self.value = value

    def __str__(self) -> str:
        if self.value is None:
            return f"missing value for parameter {self.name}"
        elif self.value == "":
            return f"empty value for parameter {self.name}"
        else:
            return f"invalid value for parameter {self.name}: {self.value}"


class RedirectHandshake(InvalidHandshake):
    """
    Raised when a handshake gets redirected.

    This exception is an implementation detail.

    """

    def __init__(self, uri: str) -> None:
        self.uri = uri

    def __str__(self) -> str:
        return f"redirect to {self.uri}"


class InvalidState(WebSocketException, AssertionError):
    """
    Raised when an operation is forbidden in the current state.

    This exception is an implementation detail.

    It should never be raised in normal circumstances.

    """


class InvalidURI(WebSocketException):
    """
    Raised when connecting to a URI that isn't a valid WebSocket URI.

    """

    def __init__(self, uri: str, msg: str) -> None:
        self.uri = uri
        self.msg = msg

    def __str__(self) -> str:
        return f"{self.uri} isn't a valid URI: {self.msg}"


class PayloadTooBig(WebSocketException):
    """
    Raised when receiving a frame with a payload exceeding the maximum size.

    """


class ProtocolError(WebSocketException):
    """
    Raised when a frame breaks the protocol.

    """


# When type checking, import non-deprecated aliases eagerly. Else, import on demand.
if typing.TYPE_CHECKING:
    from .legacy.exceptions import (
        AbortHandshake,
        InvalidMessage,
        InvalidStatusCode,
    )

    WebSocketProtocolError = ProtocolError
else:
    lazy_import(
        globals(),
        aliases={
            "AbortHandshake": ".legacy.exceptions",
            "InvalidMessage": ".legacy.exceptions",
            "InvalidStatusCode": ".legacy.exceptions",
            "WebSocketProtocolError": ".legacy.exceptions",
        },
    )
