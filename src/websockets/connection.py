from __future__ import annotations

import enum
import logging
import uuid
from typing import Generator, List, Optional, Type, Union

from .exceptions import (
    ConnectionClosed,
    ConnectionClosedError,
    ConnectionClosedOK,
    InvalidState,
    PayloadTooBig,
    ProtocolError,
)
from .extensions import Extension
from .frames import (
    OK_CLOSE_CODES,
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

        # Connnection state. Initially OPEN because subclasses handle CONNECTING.
        self.state = state

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
    def state(self) -> State:
        """
        Connection State defined in 4.1, 4.2, 7.1.3, and 7.1.4 of :rfc:`6455`.

        """
        return self._state

    @state.setter
    def state(self, state: State) -> None:
        if self.debug:
            self.logger.debug("= connection is %s", state.name)
        self._state = state

    @property
    def close_code(self) -> Optional[int]:
        """
        Connection Close Code defined in 7.1.5 of :rfc:`6455`.

        Available once the connection is closed.

        """
        if self.state is not CLOSED:
            return None
        elif self.close_rcvd is None:
            return 1006
        else:
            return self.close_rcvd.code

    @property
    def close_reason(self) -> Optional[str]:
        """
        Connection Close Reason defined in 7.1.6 of :rfc:`6455`.

        Available once the connection is closed.

        """
        if self.state is not CLOSED:
            return None
        elif self.close_rcvd is None:
            return ""
        else:
            return self.close_rcvd.reason

    @property
    def close_exc(self) -> ConnectionClosed:
        """
        Exception raised when trying to interact with a closed connection.

        Available once the connection is closed. If you need to raise this
        exception while the connection is closing, wait until it's closed.

        """
        assert self.state is CLOSED
        exc_type: Type[ConnectionClosed]
        if (
            self.close_rcvd is not None
            and self.close_sent is not None
            and self.close_rcvd.code in OK_CLOSE_CODES
            and self.close_sent.code in OK_CLOSE_CODES
        ):
            exc_type = ConnectionClosedOK
        else:
            exc_type = ConnectionClosedError
        exc: ConnectionClosed = exc_type(
            self.close_rcvd,
            self.close_sent,
            self.close_rcvd_then_sent,
        )
        # Chain to the exception raised in the parser, if any.
        exc.__cause__ = self.parser_exc
        return exc

    # Public methods for receiving data.

    def receive_data(self, data: bytes) -> None:
        """
        Receive data from the connection.

        After calling this method:

        - You must call :meth:`data_to_send` and send this data.
        - You should call :meth:`events_received` and process these events.

        Raises:
            EOFError: if :meth:`receive_eof` was called before.

        """
        self.reader.feed_data(data)
        next(self.parser)

    def receive_eof(self) -> None:
        """
        Receive the end of the data stream from the connection.

        After calling this method:

        - You must call :meth:`data_to_send` and send this data.
        - You aren't exepcted to call :meth:`events_received` as it won't
          return any new events.

        Raises:
            EOFError: if :meth:`receive_eof` was called before.

        """
        self.reader.feed_eof()
        next(self.parser)

    # Public methods for sending events.

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
                raise ProtocolError("cannot send a reason without a code")
            close = Close(1005, "")
            data = b""
        else:
            close = Close(code, reason)
            data = close.serialize()
        # send_frame() guarantees that self.state is OPEN at this point.
        # 7.1.3. The WebSocket Closing Handshake is Started
        self.send_frame(Frame(OP_CLOSE, data))
        self.close_sent = close
        self.state = CLOSING

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

    def fail(self, code: int, reason: str = "") -> None:
        """
        Fail the WebSocket connection.

        """
        # 7.1.7. Fail the WebSocket Connection

        # Send a close frame when the state is OPEN (a close frame was already
        # sent if it's CLOSING), except when failing the connection because
        # of an error reading from or writing to the network.
        if self.state is OPEN:
            if code != 1006:
                close = Close(code, reason)
                data = close.serialize()
                self.send_frame(Frame(OP_CLOSE, data))
                self.close_sent = close
                self.state = CLOSING

        # When failing the connection, a server closes the TCP connection
        # without waiting for the client to complete the handshake, while a
        # client waits for the server to close the TCP connection, possibly
        # after sending a close frame that the client will ignore.
        if self.side is SERVER and not self.eof_sent:
            self.send_eof()

        # 7.1.7. Fail the WebSocket Connection "An endpoint MUST NOT continue
        # to attempt to process data(including a responding Close frame) from
        # the remote endpoint after being instructed to _Fail the WebSocket
        # Connection_."
        self.parser = self.discard()
        next(self.parser)  # start coroutine

    # Public method for getting incoming events after receiving data.

    def events_received(self) -> List[Event]:
        """
        Return events read from the connection.

        Call this method immediately after calling any of the ``receive_*()``
        methods and process the events.

        """
        events, self.events = self.events, []
        return events

    # Public method for getting outgoing data after receiving data or sending events.

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

    def close_expected(self) -> bool:
        """
        Tell whether the TCP connection is expected to close soon.

        Call this method immediately after calling any of the ``receive_*()``
        or ``fail_*()``  methods and, if it returns :obj:`True`, schedule
        closing the TCP connection after a short timeout.

        """
        # We already got a TCP Close if and only if the state is CLOSED.
        # We expect a TCP close if and only if we sent a close frame:
        # * Normal closure: once we send a close frame, we expect a TCP close:
        #   server waits for client to complete the TCP closing handshake;
        #   client waits for server to initiate the TCP closing handshake.
        # * Abnormal closure: we always send a close frame and the same logic
        #   applies, except on EOFError where we don't send a close frame
        #   because we already received the TCP close, so we don't expect it.
        return self.state is not CLOSED and self.close_sent is not None

    # Private methods for receiving data.

    def parse(self) -> Generator[None, None, None]:
        """
        Parse incoming data into frames.

        :meth:`receive_data` and :meth:`receive_eof` run this generator
        coroutine until it needs more data or reaches EOF.

        """
        try:
            while True:
                if (yield from self.reader.at_eof()):
                    if self.debug:
                        self.logger.debug("< EOF")
                    # If the WebSocket connection is closed cleanly, with a
                    # closing handhshake, recv_frame() substitutes parse()
                    # with discard(). This branch is reached only when the
                    # connection isn't closed cleanly.
                    raise EOFError("unexpected end of stream")

                if self.max_size is None:
                    max_size = None
                elif self.cur_size is None:
                    max_size = self.max_size
                else:
                    max_size = self.max_size - self.cur_size

                # During a normal closure, execution ends here on the next
                # iteration of the loop after receiving a close frame. At
                # this point, recv_frame() replaced parse() by discard().
                frame = yield from Frame.parse(
                    self.reader.read_exact,
                    mask=self.side is SERVER,
                    max_size=max_size,
                    extensions=self.extensions,
                )

                if self.debug:
                    self.logger.debug("< %s", frame)

                self.recv_frame(frame)

        except ProtocolError as exc:
            self.fail(1002, str(exc))
            self.parser_exc = exc

        except EOFError as exc:
            self.fail(1006, str(exc))
            self.parser_exc = exc

        except UnicodeDecodeError as exc:
            self.fail(1007, f"{exc.reason} at position {exc.start}")
            self.parser_exc = exc

        except PayloadTooBig as exc:
            self.fail(1009, str(exc))
            self.parser_exc = exc

        except Exception as exc:
            self.logger.error("parser failed", exc_info=True)
            # Don't include exception details, which may be security-sensitive.
            self.fail(1011)
            self.parser_exc = exc

        # During an abnormal closure, execution ends here after catching an
        # exception. At this point, fail() replaced parse() by discard().
        yield
        raise AssertionError("parse() shouldn't step after error")  # pragma: no cover

    def discard(self) -> Generator[None, None, None]:
        """
        Discard incoming data.

        This coroutine replaces :meth:`parse`:

        - after receiving a close frame, during a normal closure (1.4);
        - after sending a close frame, during an abnormal closure (7.1.7).

        """
        # The server close the TCP connection in the same circumstances where
        # discard() replaces parse(). The client closes the connection later,
        # after the server closes the connection or a timeout elapses.
        # (The latter case cannot be handled in this Sans-I/O layer.)
        assert (self.side is SERVER) == (self.eof_sent)
        while not (yield from self.reader.at_eof()):
            self.reader.discard()
        if self.debug:
            self.logger.debug("< EOF")
        # A server closes the TCP connection immediately, while a client
        # waits for the server to close the TCP connection.
        if self.side is CLIENT:
            self.send_eof()
        self.state = CLOSED
        # If discard() completes normally, execution ends here.
        yield
        # Once the reader reaches EOF, its feed_data/eof() methods raise an
        # error, so our receive_data/eof() methods don't step the generator.
        raise AssertionError("discard() shouldn't step after EOF")  # pragma: no cover

    def recv_frame(self, frame: Frame) -> None:
        """
        Process an incoming frame.

        """
        if frame.opcode is OP_TEXT or frame.opcode is OP_BINARY:
            if self.cur_size is not None:
                raise ProtocolError("expected a continuation frame")
            if frame.fin:
                self.cur_size = None
            else:
                self.cur_size = len(frame.data)

        elif frame.opcode is OP_CONT:
            if self.cur_size is None:
                raise ProtocolError("unexpected continuation frame")
            if frame.fin:
                self.cur_size = None
            else:
                self.cur_size += len(frame.data)

        elif frame.opcode is OP_PING:
            # 5.5.2. Ping: "Upon receipt of a Ping frame, an endpoint MUST
            # send a Pong frame in response"
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
                self.state = CLOSING

            # 7.1.2. Start the WebSocket Closing Handshake: "Once an
            # endpoint has both sent and received a Close control frame,
            # that endpoint SHOULD _Close the WebSocket Connection_"

            # A server closes the TCP connection immediately, while a client
            # waits for the server to close the TCP connection.
            if self.side is SERVER:
                self.send_eof()

            # 1.4. Closing Handshake: "after receiving a control frame
            # indicating the connection should be closed, a peer discards
            # any further data received."
            self.parser = self.discard()
            next(self.parser)  # start coroutine

        else:  # pragma: no cover
            # This can't happen because Frame.parse() validates opcodes.
            raise AssertionError(f"unexpected opcode: {frame.opcode:02x}")

        self.events.append(frame)

    # Private methods for sending events.

    def send_frame(self, frame: Frame) -> None:
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
