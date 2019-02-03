from typing import Union


__all__ = ["Data"]

Data = Union[str, bytes]

Data__doc__ = """
Types supported in a WebSocket message:

- :class:`str` for text messages
- :class:`bytes` for binary messages

"""

try:
    Data.__doc__ = Data__doc__  # type: ignore
except AttributeError:  # pragma: no cover
    pass
