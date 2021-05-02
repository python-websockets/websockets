from typing import List, NewType, Optional, Tuple, Union


__all__ = ["Data", "Origin", "ExtensionHeader", "ExtensionParameter", "Subprotocol"]

Data = Union[str, bytes]
Data.__doc__ = """
Types supported in a WebSocket message:

- :class:`str` for text messages
- :class:`bytes` for binary messages

"""


Origin = NewType("Origin", str)
Origin.__doc__ = """Value of a Origin header"""


ExtensionName = NewType("ExtensionName", str)
ExtensionName.__doc__ = """Name of a WebSocket extension"""


ExtensionParameter = Tuple[str, Optional[str]]
ExtensionParameter.__doc__ = """Parameter of a WebSocket extension"""


ExtensionHeader = Tuple[ExtensionName, List[ExtensionParameter]]
ExtensionHeader.__doc__ = """Extension in a Sec-WebSocket-Extensions header"""


Subprotocol = NewType("Subprotocol", str)
Subprotocol.__doc__ = """Subprotocol value in a Sec-WebSocket-Protocol header"""


ConnectionOption = NewType("ConnectionOption", str)
ConnectionOption.__doc__ = """Connection option in a Connection header"""


UpgradeProtocol = NewType("UpgradeProtocol", str)
UpgradeProtocol.__doc__ = """Upgrade protocol in an Upgrade header"""
