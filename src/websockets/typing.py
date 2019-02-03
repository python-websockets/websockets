from typing import List, NewType, Optional, Tuple, Union


__all__ = ["Data", "Origin", "ExtensionHeader", "ExtensionParameter", "Subprotocol"]

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


Origin = NewType("Origin", str)

ExtensionParameter = Tuple[str, Optional[str]]

ExtensionHeader = Tuple[str, List[ExtensionParameter]]

Subprotocol = NewType("Subprotocol", str)
