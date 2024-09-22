from .utils import DeprecationTestCase


class BackwardsCompatibilityTests(DeprecationTestCase):
    def test_headers_class(self):
        with self.assertDeprecationWarning(
            "websockets.auth, an alias for websockets.legacy.auth, is deprecated; "
            "see https://websockets.readthedocs.io/en/stable/howto/upgrade.html "
            "for upgrade instructions",
        ):
            from websockets.auth import (
                BasicAuthWebSocketServerProtocol,  # noqa: F401
                basic_auth_protocol_factory,  # noqa: F401
            )
