__all__ = [
    'InvalidHandshake', 'InvalidState', 'InvalidURI',
    'PayloadTooBig', 'WebSocketProtocolError',
]


class InvalidHandshake(Exception):
    """Exception raised when a handshake request or response is invalid."""


class InvalidState(Exception):
    """Exception raised when an operation is forbidden in the current state."""


class InvalidURI(Exception):
    """Exception raised when an URI isn't a valid websocket URI."""


class PayloadTooBig(Exception):
    """Exception raised when a frame's payload exceeds the maximum size."""


class WebSocketProtocolError(Exception):
    """Internal exception raised when the remote side breaks the protocol."""
