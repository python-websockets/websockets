from ..exceptions import (
    InvalidHandshake,
    ProtocolError as WebSocketProtocolError,  # noqa: F401
)


class InvalidMessage(InvalidHandshake):
    """
    Raised when a handshake request or response is malformed.

    """
