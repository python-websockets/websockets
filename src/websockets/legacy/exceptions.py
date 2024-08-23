from ..exceptions import InvalidHandshake


class InvalidMessage(InvalidHandshake):
    """
    Raised when a handshake request or response is malformed.

    """
