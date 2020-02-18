import enum
from typing import Generator, Iterable, List, Tuple

from .events import Event
from .exceptions import InvalidState
from .streams import StreamReader


__all__ = ["Connection"]


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

    def receive_data(self, data: bytes) -> Tuple[Iterable[Event], bytes]:
        self.reader.feed_data(data)
        return self.receive()

    def receive_eof(self) -> Tuple[Iterable[Event], bytes]:
        self.reader.feed_eof()
        return self.receive()

    # Public APIs for receiving events and producing data

    def send(self, event: Event) -> bytes:
        """
        Send an event to the remote endpoint.

        """
        if self.state == OPEN:
            raise NotImplementedError  # not implemented yet
        elif self.state == CONNECTING:
            return self.send_in_connecting_state(event)
        else:
            raise InvalidState(
                f"Cannot write to a WebSocket in the {self.state.name} state"
            )

    # Private APIs

    def send_in_connecting_state(self, event: Event) -> bytes:
        raise NotImplementedError

    def receive(self) -> Tuple[List[Event], bytes]:
        # Run parser until more data is needed or EOF
        try:
            next(self.parser)
        except StopIteration:
            pass
        events, self.events = self.events, []
        return events, b""

    def parse(self) -> Generator[None, None, None]:
        yield  # not implemented yet
