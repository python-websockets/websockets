from websockets.datastructures import Headers

from .utils import DeprecationTestCase


class BackwardsCompatibilityTests(DeprecationTestCase):
    def test_headers_class(self):
        with self.assertDeprecationWarning(
            "Headers and MultipleValuesError were moved "
            "from websockets.http to websockets.datastructures"
            "and read_request and read_response were moved "
            "from websockets.http to websockets.legacy.http",
        ):
            from websockets.http import Headers as OldHeaders

        self.assertIs(OldHeaders, Headers)
