__all__ = ['InvalidHandshake', 'InvalidState', 'InvalidURI']


class InvalidHandshake(Exception):
    """Exception raised when a handshake request or response is invalid."""


class InvalidState(Exception):
    """Exception raised when an operation is forbidden in the current state."""


class InvalidURI(Exception):
    """Exception raised when an URI is invalid."""

class PayloadTooLarge(Exception):
    """Exception raised when a message exceeds maximum size"""
    pass

class WebSocketProtocolError(Exception):
    # Internal exception raised when the other end breaks the protocol.
    # It's private because it shouldn't leak outside of WebSocketCommonProtocol.
    pass

