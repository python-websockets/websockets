from __future__ import annotations

import enum
import logging
import uuid
from typing import Generator, List, Optional, Union

from .exceptions import InvalidState, PayloadTooBig, ProtocolError
from .extensions import Extension
from .frames import (
    OP_BINARY,
    OP_CLOSE,
    OP_CONT,
    OP_PING,
    OP_PONG,
    OP_TEXT,
    Close,
    Frame,
)
from .http11 import Request, Response
from .streams import StreamReader
from .typing import LoggerLike, Origin, Subprotocol


__all__ = [
    "Connection",
    "Side",
    "State",
    "SEND_EOF",
]

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


# Sentinel to signal that the connection should be closed.

SEND_EOF = b""


class Connection:
    def __init__(
        self,
        side: Side,
        state: State = OPEN,
        max_size: Optional[int] = 2 ** 20,
        logger: Optional[LoggerLike] = None,
    ) -> None:
        # Unique identifier. For logs.
        self.id = uuid.uuid4()

        # Logger or LoggerAdapter for this connection.
        if logger is None:
            logger = logging.getLogger(f"websockets.{side.name.lower()}")
        self.logger = logger

        # Track if DEBUG is enabled. Shortcut logging calls if it isn't.
        self.debug = logger.isEnabledFor(logging.DEBUG)

        # Connection side. CLIENT or SERVER.
        self.side = side

        # Connnection state. CONNECTING and CLOSED states are handled in subclasses.
        self.set_state(state)

        # Maximum size of incoming messages in bytes.
        self.max_size = max_size

        # Current size of incoming message in bytes. Only set while reading a
        # fragmented message i.e. a data frames with the FIN bit not set.
        self.cur_size: Optional[int] = None

        # True while sending a fragmented message i.e. a data frames with the
        # FIN bit not set.
        self.expect_continuation_frame = False

        # WebSocket protocol parameters.
        self.origin: Optional[Origin] = None
        self.extensions: List[Extension] = []
        self.subprotocol: Optional[Subprotocol] = None

        # Close code and reason, set when a close frame is sent or received.
        self.close_rcvd: Optional[Close] = None
        self.close_sent: Optional[Close] = None
        self.close_rcvd_then_sent: Optional[bool] = None

        # Track if send_eof() was called.
        self.eof_sent = False

        # Parser state.
        self.reader = StreamReader()
        self.events: List[Event] = []
        self.writes: List[bytes] = []
        self.parser = self.parse()
        next(self.parser)  # start coroutine
        self.parser_exc: Optional[Exception] = None

    # Public attributes

    @property
    def close_code(self) -> Optional[int]:
        """
        WebSocket close code received in a close frame.

        Available once the connection is closed.

        """
        if self.state is not State.CLOSED:
            return None
        elif self.close_rcvd is None:
            return 1006
        else:
            return self.close_rcvd.code

    @property
    def close_reason(self) -> Optional[str]:
        """
        WebSocket close reason received in a close frame.

        Available once the connection is closed.

        """
        if self.state is not State.CLOSED:
            return None
        elif self.close_rcvd is None:
            return ""
        else:
            return self.close_rcvd.reason

    # Private attributes

    def set_state(self, state: State) -> None:
        if self.debug:
            self.logger.debug("= connection is %s", state.name)
        self.state = state

    # Public APIs for receiving data.

    def receive_data(self, data: bytes) -> None:
        """
        Receive data from the connection.

        After calling this method:

        - You must call :meth:`data_to_send` and send this data.
        - You should call :meth:`events_received` and process these events.

        """
        self.reader.feed_data(data)
        self.step_parser()

    def receive_eof(self) -> None:
        """
        Receive the end of the data stream from the connection.

        After calling this method:

        - You must call :meth:`data_to_send` and send this data.
        - You shouldn't call :meth:`events_received` as it won't
          return any new events.

        """
        self.reader.feed_eof()
        self.step_parser()

    # Public APIs for sending events.

    def send_continuation(self, data: bytes, fin: bool) -> None:
        """
        Send a continuation frame.

        """
        if not self.expect_continuation_frame:
            raise ProtocolError("unexpected continuation frame")
        self.expect_continuation_frame = not fin
        self.send_frame(Frame(OP_CONT, data, fin))

    def send_text(self, data: bytes, fin: bool = True) -> None:
        """
        Send a text frame.

        """
        if self.expect_continuation_frame:
            raise ProtocolError("expected a continuation frame")
        self.expect_continuation_frame = not fin
        self.send_frame(Frame(OP_TEXT, data, fin))

    def send_binary(self, data: bytes, fin: bool = True) -> None:
        """
        Send a binary frame.

        """
        if self.expect_continuation_frame:
            raise ProtocolError("expected a continuation frame")
        self.expect_continuation_frame = not fin
        self.send_frame(Frame(OP_BINARY, data, fin))

    def send_close(self, code: Optional[int] = None, reason: str = "") -> None:
        """
        Send a connection close frame.

        """
        if self.expect_continuation_frame:
            raise ProtocolError("expected a continuation frame")
        if code is None:
            if reason != "":
                raise ValueError("cannot send a reason without a code")
            close = Close(1005, "")
            data = b""
        else:
            close = Close(code, reason)
            data = close.serialize()
        self.send_frame(Frame(OP_CLOSE, data))
        self.close_sent = close
        # send_frame() guarantees that self.state is OPEN at this point.
        # 7.1.3. The WebSocket Closing Handshake is Started
        self.set_state(CLOSING)

    def send_ping(self, data: bytes) -> None:
        """
        Send a ping frame.

        """
        self.send_frame(Frame(OP_PING, data))

    def send_pong(self, data: bytes) -> None:
        """
        Send a pong frame.

        """
        self.send_frame(Frame(OP_PONG, data))

    def fail(self, code: Optional[int] = None, reason: str = "") -> None:
        """
        Fail the WebSocket connection.

        """
        # 7.1.7. Fail the WebSocket Connection

        # Send a close frame when the state is OPEN (a close frame was already
        # sent if it's CLOSING), except when failing the connection because
        # of an error reading from or writing to the network.
        if self.state is OPEN and code != 1006:
            self.send_close(code, reason)

        if self.side is SERVER and not self.eof_sent:
            self.send_eof()

        # "An endpoint MUST NOT continue to attempt to process data
        # (including a responding Close frame) from the remote endpoint
        # after being instructed to _Fail the WebSocket Connection_."
        self.reader.abort()

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

    def data_to_send(self) -> List[bytes]:
        """
        Return data to write to the connection.

        Call this method immediately after calling any of the ``receive_*()``,
        ``send_*()``, or ``fail()`` methods and write the data to the
        connection.

        The empty bytestring signals the end of the data stream.

        """
        writes, self.writes = self.writes, []
        return writes

    # Private APIs for receiving data.

    def step_parser(self) -> None:
        # Run parser until more data is needed or EOF
        try:
            next(self.parser)
        except StopIteration:  # pragma: no cover
            raise AssertionError("parser shouldn't exit")
        except ProtocolError as exc:
            self.fail(1002, str(exc))
            self.parser_exc = exc
            raise
        except EOFError as exc:
            self.fail(1006, str(exc))
            self.parser_exc = exc
            raise
        except UnicodeDecodeError as exc:
            self.fail(1007, f"{exc.reason} at position {exc.start}")
            self.parser_exc = exc
            raise
        except PayloadTooBig as exc:
            self.fail(1009, str(exc))
            self.parser_exc = exc
            raise
        except Exception as exc:
            self.logger.error("parser failed", exc_info=True)
            # Don't include exception details, which may be security-sensitive.
            self.fail(1011)
            self.parser_exc = exc
            raise

    def parse(self) -> Generator[None, None, None]:
        while True:
            eof = yield from self.reader.at_eof()
            if eof:
                if self.debug:
                    self.logger.debug("< EOF")
                if self.close_rcvd is not None:
                    if not self.eof_sent:
                        self.send_eof()
                    yield
                    # Once the reader reaches EOF, its feed_data/eof() methods
                    # raise an error, so our receive_data/eof() methods never
                    # call step_parser(), so the generator shouldn't resume
                    # executing until it's garbage collected.
                    raise AssertionError(
                        "parser shouldn't step after EOF"
                    )  # pragma: no cover
                else:
                    raise EOFError("unexpected end of stream")

            if self.max_size is None:
                max_size = None
            elif self.cur_size is None:
                max_size = self.max_size
            else:
                max_size = self.max_size - self.cur_size

            frame = yield from Frame.parse(
                self.reader.read_exact,
                mask=self.side is SERVER,
                max_size=max_size,
                extensions=self.extensions,
            )

            if self.debug:
                self.logger.debug("< %s", frame)

            if frame.opcode is OP_TEXT or frame.opcode is OP_BINARY:
                # 5.5.1 Close: "The application MUST NOT send any more data
                # frames after sending a Close frame."
                if self.close_rcvd is not None:
                    raise ProtocolError("data frame after close frame")

                if self.cur_size is not None:
                    raise ProtocolError("expected a continuation frame")
                if frame.fin:
                    self.cur_size = None
                else:
                    self.cur_size = len(frame.data)

            elif frame.opcode is OP_CONT:
                # 5.5.1 Close: "The application MUST NOT send any more data
                # frames after sending a Close frame."
                if self.close_rcvd is not None:
                    raise ProtocolError("data frame after close frame")

                if self.cur_size is None:
                    raise ProtocolError("unexpected continuation frame")
                if frame.fin:
                    self.cur_size = None
                else:
                    self.cur_size += len(frame.data)

            elif frame.opcode is OP_PING:
                # 5.5.2. Ping: "Upon receipt of a Ping frame, an endpoint MUST
                # send a Pong frame in response, unless it already received a
                # Close frame."
                if self.close_rcvd is None:
                    pong_frame = Frame(OP_PONG, frame.data)
                    self.send_frame(pong_frame)

            elif frame.opcode is OP_PONG:
                # 5.5.3 Pong: "A response to an unsolicited Pong frame is not
                # expected."
                pass

            elif frame.opcode is OP_CLOSE:
                # 7.1.5.  The WebSocket Connection Close Code
                # 7.1.6.  The WebSocket Connection Close Reason
                self.close_rcvd = Close.parse(frame.data)
                if self.state is CLOSING:
                    assert self.close_sent is not None
                    self.close_rcvd_then_sent = False

                if self.cur_size is not None:
                    raise ProtocolError("incomplete fragmented message")

                # 5.5.1 Close: "If an endpoint receives a Close frame and did
                # not previously send a Close frame, the endpoint MUST send a
                # Close frame in response. (When sending a Close frame in
                # response, the endpoint typically echos the status code it
                # received.)"

                if self.state is OPEN:
                    # Echo the original data instead of re-serializing it with
                    # Close.serialize() because that fails when the close frame
                    # is empty and Close.parse() synthetizes a 1005 close code.
                    # The rest is identical to send_close().
                    self.send_frame(Frame(OP_CLOSE, frame.data))
                    self.close_sent = self.close_rcvd
                    self.close_rcvd_then_sent = True
                    self.set_state(CLOSING)

                # 7.1.2. Start the WebSocket Closing Handshake: "Once an
                # endpoint has both sent and received a Close control frame,
                # that endpoint SHOULD _Close the WebSocket Connection_"

                if self.side is SERVER:
                    self.send_eof()

            else:  # pragma: no cover
                # This can't happen because Frame.parse() validates opcodes.
                raise AssertionError(f"unexpected opcode: {frame.opcode:02x}")

            self.events.append(frame)

    # Private APIs for sending events.

    def send_frame(self, frame: Frame) -> None:
        # Defensive assertion for protocol compliance.
        if self.state is not OPEN:
            raise InvalidState(
                f"cannot write to a WebSocket in the {self.state.name} state"
            )

        if self.debug:
            self.logger.debug("> %s", frame)
        self.writes.append(
            frame.serialize(mask=self.side is CLIENT, extensions=self.extensions)
        )

    def send_eof(self) -> None:
        assert not self.eof_sent
        self.eof_sent = True
        if self.debug:
            self.logger.debug("> EOF")
        self.writes.append(SEND_EOF)
