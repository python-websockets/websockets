import enum
from typing import Any, Generator, List, Tuple, Union

from .exceptions import InvalidState
from .frames import Frame
from .http11 import Request, Response
from .streams import StreamReader


__all__ = ["Connection"]


Event = Union[Request, Response, Frame]


# A WebSocket connection is either a server or a client.


class Side(enum.IntEnum):
    SERVER, CLIENT = range(2)


SERVER = Side.SERVER
CLIENT = Side.CLIENT


# A WebSocket connection goes through the following four states, in order:


class State(enum.IntEnum):
    CONNECTING, OPEN, CLOSING, CLOSED = range(4)


CONNECTING = State.CONNECTING
OPEN = State.OPEN
CLOSING = State.CLOSING
CLOSED = State.CLOSED


class Connection:

    side: Side

    def __init__(self, side: Side, state: State = OPEN, **kwargs: Any) -> None:
        self.side = side
        self.state = state
        self.reader = StreamReader()
        self.events: List[Event] = []
        self.writes: List[bytes] = []
        self.parser = self.parse()
        next(self.parser)  # start coroutine

    def set_state(self, state: State) -> None:
        self.state = state

    # Public APIs for receiving data and producing events

    def receive_data(self, data: bytes) -> None:
        self.reader.feed_data(data)
        self.step_parser()

    def receive_eof(self) -> None:
        self.reader.feed_eof()
        self.step_parser()

    # Public APIs for receiving events and producing data

    def send_frame(self, frame: Frame) -> bytes:
        """
        Convert a WebSocket handshake response to bytes to send.

        """
        # Defensive assertion for protocol compliance.
        if self.state != OPEN:
            raise InvalidState(
                f"Cannot write to a WebSocket in the {self.state.name} state"
            )
        raise NotImplementedError  # not implemented yet

    # Public API for getting incoming events after receiving data.

    def events_received(self) -> List[Event]:
        """
        Return events read from the connection.

        Call this method immediately after calling any of the ``receive_*()``
        methods and process the events.

        """
        events, self.events = self.events, []
        return events

    # Public API for getting outgoing data after receiving data or sending events.

    def bytes_to_send(self) -> List[bytes]:
        """
        Return data to write to the connection.

        Call this method immediately after calling any of the ``receive_*()``
        or ``send_*()`` methods and write the data to the connection.

        The empty bytestring signals the end of the data stream.

        """
        writes, self.writes = self.writes, []
        return writes

    # Private APIs

    def receive(self) -> Tuple[List[Event], List[bytes]]:
        # Run parser until more data is needed or EOF
        try:
            next(self.parser)
        except StopIteration:
            pass
        events, self.events = self.events, []
        return events, []

    def step_parser(self) -> None:
        next(self.parser)

    def parse(self) -> Generator[None, None, None]:
        yield  # not implemented yet
