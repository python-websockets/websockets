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


combined_exports = [
    name
    for name in (
        []
        + websockets.asyncio.client.__all__
        + websockets.asyncio.server.__all__
        + websockets.client.__all__
        + websockets.datastructures.__all__
        + websockets.exceptions.__all__
        + websockets.frames.__all__
        + websockets.http11.__all__
        + websockets.protocol.__all__
        + websockets.server.__all__
        + websockets.typing.__all__
    )
    if not name.isupper()  # filter out constants
]


class ExportsTests(unittest.TestCase):
    def test_top_level_module_reexports_submodule_exports(self):
        self.assertEqual(
            set(combined_exports),
            set(websockets.__all__),
        )

    def test_submodule_exports_are_globally_unique(self):
        self.assertEqual(
            len(set(combined_exports)),
            len(combined_exports),
        )
