__all__ = [

    'AbortHandshake', 'InvalidHandshake', 'InvalidHeader', 'InvalidMessage',
    'InvalidOrigin', 'InvalidState', 'InvalidStatusCode', 'NegotiationError',
    'InvalidParameterName', 'InvalidParameterValue', 'DuplicateParameter',
    'InvalidURI', 'ConnectionClosed', 'PayloadTooBig',
    'WebSocketProtocolError',
]


class InvalidHandshake(Exception):
    """
    Exception raised when a handshake request or response is invalid.

    """


class AbortHandshake(InvalidHandshake):
    """
    Exception raised to abort a handshake and return a HTTP response.

    """
    def __init__(self, status, headers, body=None):
        self.status = status
        self.headers = headers
        self.body = body


class InvalidMessage(InvalidHandshake):
    """
    Exception raised when the HTTP message in a handshake request is malformed.

    """


class InvalidHeader(InvalidHandshake):
    """
    Exception raised when a HTTP header doesn't have the expected format.

    """
    def __init__(self, message, string, pos):
        self.string = string
        self.pos = pos
        message = "{} at {} in {}".format(message, pos, string)
        super().__init__(message)


class InvalidOrigin(InvalidHandshake):
    """
    Exception raised when the origin in a handshake request is forbidden.

    """


class InvalidStatusCode(InvalidHandshake):
    """
    Exception raised when a handshake response status code is invalid.

    Provides the integer status code in its ``status_code`` attribute.

    """
    def __init__(self, status_code):
        self.status_code = status_code
        message = "Status code not 101: {}".format(status_code)
        super().__init__(message)


class NegotiationError(InvalidHandshake):
    """
    Exception raised when negociating an extension fails.

    """


class InvalidParameterName(NegotiationError):
    """
    Exception raised when a parameter name in an extension header is invalid.

    """
    def __init__(self, name):
        self.name = name
        message = "Invalid parameter name: {}".format(name)
        super().__init__(message)


class InvalidParameterValue(NegotiationError):
    """
    Exception raised when a parameter value in an extension header is invalid.

    """
    def __init__(self, name, value):
        self.name = name
        self.value = value
        message = "Invalid value for parameter {}: {}".format(name, value)
        super().__init__(message)


class DuplicateParameter(NegotiationError):
    """
    Exception raised when a parameter name is repeated in an extension header.

    """
    def __init__(self, name):
        self.name = name
        message = "Duplicate parameter: {}".format(name)
        super().__init__(message)


class InvalidState(Exception):
    """
    Exception raised when an operation is forbidden in the current state.

    """


class ConnectionClosed(InvalidState):
    """
    Exception raised when trying to read or write on a closed connection.

    Provides the connection close code and reason in its ``code`` and
    ``reason`` attributes respectively.

    """
    def __init__(self, code, reason):
        self.code = code
        self.reason = reason
        message = "WebSocket connection is closed: "
        message += "code = {}, ".format(code) if code else "no code, "
        message += "reason = {}.".format(reason) if reason else "no reason."
        super().__init__(message)


class InvalidURI(Exception):
    """
    Exception raised when an URI isn't a valid websocket URI.

    """


class PayloadTooBig(Exception):
    """
    Exception raised when a frame's payload exceeds the maximum size.

    """


class WebSocketProtocolError(Exception):
    """
    Internal exception raised when the remote side breaks the protocol.

    """
