"""
The :mod:`websockets.extensions.base` defines abstract classes for extensions.

See https://tools.ietf.org/html/rfc6455#section-9.

"""


class ClientExtensionFactory:
    """
    Abstract class for client-side extension factories.

    Extension factories handle configuration and negotiation.

    """
    name = ...

    def get_request_params(self):
        """
        Build request parameters.

        Return a list of (name, value) pairs.

        """

    def process_response_params(self, params, accepted_extensions):
        """"
        Process response parameters.

        ``params`` are a list of (name, value) pairs.

        ``accepted_extensions`` is a list of previously accepted extensions,
        represented by extension instances.

        Return an extension instance (an instance of a subclass of
        :class:`Extension`) to accept this response or ``None`` to reject it.

        Raise :exc:`~websockets.exceptions.NegotiationError` to abort the
        handshake and fail the WebSocket connection.

        """


class ServerExtensionFactory:
    """
    Abstract class for server-side extension factories.

    Extension factories handle configuration and negotiation.

    """
    name = ...

    def process_request_params(self, params, accepted_extensions):
        """"
        Process request parameters.

        ``accepted_extensions`` is a list of previously accepted extensions,
        represented by extension instances.

        Return response params and an extension instance to accept this
        extension or ``None, None`` to reject it.

        Return response params (a list of (name, value) pairs) and an
        extension instance (an instance of a subclass of :class:`Extension`)
        to accept this response or ``None, None`` to reject it.

        Raise :exc:`~websockets.exceptions.NegotiationError` to abort the
        handshake and fail the websocket connection.

        """


class Extension:
    """
    Abstract class for extensions.

    """
    name = ...

    def decode(self, frame):
        """
        Decode an incoming frame.

        """
        return frame

    def encode(self, frame):
        """
        Encode an outgoing frame.

        """
        return frame
