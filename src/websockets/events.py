from typing import NamedTuple, Optional, Union

from .http11 import Request, Response


__all__ = [
    "Accept",
    "Connect",
    "Event",
    "Reject",
]


class Connect(NamedTuple):
    request: Request


class Accept(NamedTuple):
    response: Response


class Reject(NamedTuple):
    response: Response
    exception: Optional[Exception]


Event = Union[Connect, Accept, Reject]
