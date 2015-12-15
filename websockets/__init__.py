# This relies on each of the submodules having an __all__ variable.

from .client import *
from .exceptions import *
from .protocol import *
from .server import *
from .uri import *

__all__ = (
    client.__all__
    + exceptions.__all__
    + protocol.__all__
    + server.__all__
    + uri.__all__
)

try:
    from .python35 import Connect as connect
except (ImportError, SyntaxError):
    connect = client._connect

from .version import version as __version__                             # noqa
