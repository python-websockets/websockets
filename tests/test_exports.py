import unittest

import websockets
import websockets.asyncio.client
import websockets.asyncio.server
import websockets.client
import websockets.datastructures
import websockets.exceptions
import websockets.server
import websockets.typing
import websockets.uri


combined_exports = (
    []
    + websockets.asyncio.client.__all__
    + websockets.asyncio.server.__all__
    + websockets.client.__all__
    + websockets.datastructures.__all__
    + websockets.exceptions.__all__
    + websockets.server.__all__
    + websockets.typing.__all__
)

# These API are intentionally not re-exported by the top-level module.
missing_reexports = [
    # websockets.asyncio.client
    "ClientConnection",
    # websockets.asyncio.server
    "ServerConnection",
    "Server",
]


class ExportsTests(unittest.TestCase):
    def test_top_level_module_reexports_submodule_exports(self):
        self.assertEqual(
            set(combined_exports),
            set(websockets.__all__ + missing_reexports),
        )

    def test_submodule_exports_are_globally_unique(self):
        self.assertEqual(
            len(set(combined_exports)),
            len(combined_exports),
        )
