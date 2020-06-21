import enum
from typing import Generator, List, Tuple, Union

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

    def __init__(self, state: State = OPEN) -> None:
        self.state = state
        self.reader = StreamReader()
        self.events: List[Event] = []
        self.parser = self.parse()
        next(self.parser)  # start coroutine

    # Public APIs for receiving data and producing events

    def receive_data(self, data: bytes) -> Tuple[List[Event], List[bytes]]:
        self.reader.feed_data(data)
        return self.receive()

    def receive_eof(self) -> Tuple[List[Event], List[bytes]]:
        self.reader.feed_eof()
        return self.receive()

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

    # Private APIs

    def receive(self) -> Tuple[List[Event], List[bytes]]:
        # Run parser until more data is needed or EOF
        try:
            next(self.parser)
        except StopIteration:
            pass
        events, self.events = self.events, []
        return events, []

    def parse(self) -> Generator[None, None, None]:
        yield  # not implemented yet
