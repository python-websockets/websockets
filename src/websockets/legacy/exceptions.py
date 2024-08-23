from .. import datastructures
from ..exceptions import (
    InvalidHandshake,
    ProtocolError as WebSocketProtocolError,  # noqa: F401
)


class InvalidMessage(InvalidHandshake):
    """
    Raised when a handshake request or response is malformed.

    """


class InvalidStatusCode(InvalidHandshake):
    """
    Raised when a handshake response status code is invalid.

    """

    def __init__(self, status_code: int, headers: datastructures.Headers) -> None:
        self.status_code = status_code
        self.headers = headers

    def __str__(self) -> str:
        return f"server rejected WebSocket connection: HTTP {self.status_code}"
