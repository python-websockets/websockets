import http
import unittest
import unittest.mock

from websockets.connection import CONNECTING, OPEN
from websockets.datastructures import Headers
from websockets.events import Accept, Connect, Reject
from websockets.exceptions import InvalidHeader, InvalidOrigin, InvalidUpgrade
from websockets.http import USER_AGENT
from websockets.http11 import Request, Response
from websockets.server import *

from .extensions.utils import (
    OpExtension,
    Rsv2Extension,
    ServerOpExtensionFactory,
    ServerRsv2ExtensionFactory,
)
from .test_utils import ACCEPT, KEY
from .utils import DATE


class ConnectTests(unittest.TestCase):
    def test_receive_connect(self):
        server = ServerConnection()
        [connect], bytes_to_send = server.receive_data(
            (
                f"GET /test HTTP/1.1\r\n"
                f"Host: example.com\r\n"
                f"Upgrade: websocket\r\n"
                f"Connection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {KEY}\r\n"
                f"Sec-WebSocket-Version: 13\r\n"
                f"User-Agent: {USER_AGENT}\r\n"
                f"\r\n"
            ).encode(),
        )
        self.assertIsInstance(connect, Connect)
        self.assertEqual(bytes_to_send, b"")

    def test_connect_request(self):
        server = ServerConnection()
        [connect], bytes_to_send = server.receive_data(
            (
                f"GET /test HTTP/1.1\r\n"
                f"Host: example.com\r\n"
                f"Upgrade: websocket\r\n"
                f"Connection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {KEY}\r\n"
                f"Sec-WebSocket-Version: 13\r\n"
                f"User-Agent: {USER_AGENT}\r\n"
                f"\r\n"
            ).encode(),
        )
        self.assertEqual(connect.request.path, "/test")
        self.assertEqual(
            connect.request.headers,
            Headers(
                {
                    "Host": "example.com",
                    "Upgrade": "websocket",
                    "Connection": "Upgrade",
                    "Sec-WebSocket-Key": KEY,
                    "Sec-WebSocket-Version": "13",
                    "User-Agent": USER_AGENT,
                }
            ),
        )


class AcceptRejectTests(unittest.TestCase):
    def make_connect_request(self):
        return Request(
            path="/test",
            headers=Headers(
                {
                    "Host": "example.com",
                    "Upgrade": "websocket",
                    "Connection": "Upgrade",
                    "Sec-WebSocket-Key": KEY,
                    "Sec-WebSocket-Version": "13",
                    "User-Agent": USER_AGENT,
                }
            ),
        )

    def test_send_accept(self):
        server = ServerConnection()
        with unittest.mock.patch("email.utils.formatdate", return_value=DATE):
            accept = server.accept(Connect(self.make_connect_request()))
        self.assertIsInstance(accept, Accept)
        bytes_to_send = server.send(accept)
        self.assertEqual(
            bytes_to_send,
            (
                f"HTTP/1.1 101 Switching Protocols\r\n"
                f"Upgrade: websocket\r\n"
                f"Connection: Upgrade\r\n"
                f"Sec-WebSocket-Accept: {ACCEPT}\r\n"
                f"Date: {DATE}\r\n"
                f"Server: {USER_AGENT}\r\n"
                f"\r\n"
            ).encode(),
        )
        self.assertEqual(server.state, OPEN)

    def test_send_reject(self):
        server = ServerConnection()
        with unittest.mock.patch("email.utils.formatdate", return_value=DATE):
            reject = server.reject(http.HTTPStatus.NOT_FOUND, "Sorry folks.\n")
        self.assertIsInstance(reject, Reject)
        bytes_to_send = server.send(reject)
        self.assertEqual(
            bytes_to_send,
            (
                f"HTTP/1.1 404 Not Found\r\n"
                f"Date: {DATE}\r\n"
                f"Server: {USER_AGENT}\r\n"
                f"Content-Length: 13\r\n"
                f"Content-Type: text/plain; charset=utf-8\r\n"
                f"Connection: close\r\n"
                f"\r\n"
                f"Sorry folks.\n"
            ).encode(),
        )
        self.assertEqual(server.state, CONNECTING)

    def test_accept_response(self):
        server = ServerConnection()
        with unittest.mock.patch("email.utils.formatdate", return_value=DATE):
            accept = server.accept(Connect(self.make_connect_request()))
        self.assertIsInstance(accept.response, Response)
        self.assertEqual(accept.response.status_code, 101)
        self.assertEqual(accept.response.reason_phrase, "Switching Protocols")
        self.assertEqual(
            accept.response.headers,
            Headers(
                {
                    "Upgrade": "websocket",
                    "Connection": "Upgrade",
                    "Sec-WebSocket-Accept": ACCEPT,
                    "Date": DATE,
                    "Server": USER_AGENT,
                }
            ),
        )
        self.assertIsNone(accept.response.body)

    def test_reject_response(self):
        server = ServerConnection()
        with unittest.mock.patch("email.utils.formatdate", return_value=DATE):
            reject = server.reject(http.HTTPStatus.NOT_FOUND, "Sorry folks.\n")
        self.assertIsInstance(reject.response, Response)
        self.assertEqual(reject.response.status_code, 404)
        self.assertEqual(reject.response.reason_phrase, "Not Found")
        self.assertEqual(
            reject.response.headers,
            Headers(
                {
                    "Date": DATE,
                    "Server": USER_AGENT,
                    "Content-Length": "13",
                    "Content-Type": "text/plain; charset=utf-8",
                    "Connection": "close",
                }
            ),
        )
        self.assertEqual(reject.response.body, b"Sorry folks.\n")

    def test_basic(self):
        server = ServerConnection()
        request = self.make_connect_request()
        accept = server.accept(Connect(request))

        self.assertIsInstance(accept, Accept)

    def test_unexpected_exception(self):
        server = ServerConnection()
        request = self.make_connect_request()
        with unittest.mock.patch(
            "websockets.server.ServerConnection.process_request",
            side_effect=Exception("BOOM"),
        ):
            reject = server.accept(Connect(request))

        self.assertIsInstance(reject, Reject)
        self.assertEqual(reject.response.status_code, 500)
        with self.assertRaises(Exception) as raised:
            raise reject.exception
        self.assertEqual(str(raised.exception), "BOOM")

    def test_missing_connection(self):
        server = ServerConnection()
        request = self.make_connect_request()
        del request.headers["Connection"]
        reject = server.accept(Connect(request))

        self.assertIsInstance(reject, Reject)
        self.assertEqual(reject.response.status_code, 426)
        self.assertEqual(reject.response.headers["Upgrade"], "websocket")
        with self.assertRaises(InvalidUpgrade) as raised:
            raise reject.exception
        self.assertEqual(str(raised.exception), "missing Connection header")

    def test_invalid_connection(self):
        server = ServerConnection()
        request = self.make_connect_request()
        del request.headers["Connection"]
        request.headers["Connection"] = "close"
        reject = server.accept(Connect(request))

        self.assertIsInstance(reject, Reject)
        self.assertEqual(reject.response.status_code, 426)
        self.assertEqual(reject.response.headers["Upgrade"], "websocket")
        with self.assertRaises(InvalidUpgrade) as raised:
            raise reject.exception
        self.assertEqual(str(raised.exception), "invalid Connection header: close")

    def test_missing_upgrade(self):
        server = ServerConnection()
        request = self.make_connect_request()
        del request.headers["Upgrade"]
        reject = server.accept(Connect(request))

        self.assertIsInstance(reject, Reject)
        self.assertEqual(reject.response.status_code, 426)
        self.assertEqual(reject.response.headers["Upgrade"], "websocket")
        with self.assertRaises(InvalidUpgrade) as raised:
            raise reject.exception
        self.assertEqual(str(raised.exception), "missing Upgrade header")

    def test_invalid_upgrade(self):
        server = ServerConnection()
        request = self.make_connect_request()
        del request.headers["Upgrade"]
        request.headers["Upgrade"] = "h2c"
        reject = server.accept(Connect(request))

        self.assertIsInstance(reject, Reject)
        self.assertEqual(reject.response.status_code, 426)
        self.assertEqual(reject.response.headers["Upgrade"], "websocket")
        with self.assertRaises(InvalidUpgrade) as raised:
            raise reject.exception
        self.assertEqual(str(raised.exception), "invalid Upgrade header: h2c")

    def test_missing_key(self):
        server = ServerConnection()
        request = self.make_connect_request()
        del request.headers["Sec-WebSocket-Key"]
        reject = server.accept(Connect(request))

        self.assertIsInstance(reject, Reject)
        self.assertEqual(reject.response.status_code, 400)
        with self.assertRaises(InvalidHeader) as raised:
            raise reject.exception
        self.assertEqual(str(raised.exception), "missing Sec-WebSocket-Key header")

    def test_multiple_key(self):
        server = ServerConnection()
        request = self.make_connect_request()
        request.headers["Sec-WebSocket-Key"] = KEY
        reject = server.accept(Connect(request))

        self.assertIsInstance(reject, Reject)
        self.assertEqual(reject.response.status_code, 400)
        with self.assertRaises(InvalidHeader) as raised:
            raise reject.exception
        self.assertEqual(
            str(raised.exception),
            "invalid Sec-WebSocket-Key header: "
            "more than one Sec-WebSocket-Key header found",
        )

    def test_invalid_key(self):
        server = ServerConnection()
        request = self.make_connect_request()
        del request.headers["Sec-WebSocket-Key"]
        request.headers["Sec-WebSocket-Key"] = "not Base64 data!"
        reject = server.accept(Connect(request))

        self.assertIsInstance(reject, Reject)
        self.assertEqual(reject.response.status_code, 400)
        with self.assertRaises(InvalidHeader) as raised:
            raise reject.exception
        self.assertEqual(
            str(raised.exception), "invalid Sec-WebSocket-Key header: not Base64 data!"
        )

    def test_truncated_key(self):
        server = ServerConnection()
        request = self.make_connect_request()
        del request.headers["Sec-WebSocket-Key"]
        request.headers["Sec-WebSocket-Key"] = KEY[
            :16
        ]  # 12 bytes instead of 16, Base64-encoded
        reject = server.accept(Connect(request))

        self.assertIsInstance(reject, Reject)
        self.assertEqual(reject.response.status_code, 400)
        with self.assertRaises(InvalidHeader) as raised:
            raise reject.exception
        self.assertEqual(
            str(raised.exception), f"invalid Sec-WebSocket-Key header: {KEY[:16]}"
        )

    def test_missing_version(self):
        server = ServerConnection()
        request = self.make_connect_request()
        del request.headers["Sec-WebSocket-Version"]
        reject = server.accept(Connect(request))

        self.assertIsInstance(reject, Reject)
        self.assertEqual(reject.response.status_code, 400)
        with self.assertRaises(InvalidHeader) as raised:
            raise reject.exception
        self.assertEqual(str(raised.exception), "missing Sec-WebSocket-Version header")

    def test_multiple_version(self):
        server = ServerConnection()
        request = self.make_connect_request()
        request.headers["Sec-WebSocket-Version"] = "11"
        reject = server.accept(Connect(request))

        self.assertIsInstance(reject, Reject)
        self.assertEqual(reject.response.status_code, 400)
        with self.assertRaises(InvalidHeader) as raised:
            raise reject.exception
        self.assertEqual(
            str(raised.exception),
            "invalid Sec-WebSocket-Version header: "
            "more than one Sec-WebSocket-Version header found",
        )

    def test_invalid_version(self):
        server = ServerConnection()
        request = self.make_connect_request()
        del request.headers["Sec-WebSocket-Version"]
        request.headers["Sec-WebSocket-Version"] = "11"
        reject = server.accept(Connect(request))

        self.assertIsInstance(reject, Reject)
        self.assertEqual(reject.response.status_code, 400)
        with self.assertRaises(InvalidHeader) as raised:
            raise reject.exception
        self.assertEqual(
            str(raised.exception), "invalid Sec-WebSocket-Version header: 11"
        )

    def test_no_origin(self):
        server = ServerConnection(origins=["https://example.com"])
        request = self.make_connect_request()
        reject = server.accept(Connect(request))

        self.assertIsInstance(reject, Reject)
        self.assertEqual(reject.response.status_code, 403)
        with self.assertRaises(InvalidOrigin) as raised:
            raise reject.exception
        self.assertEqual(str(raised.exception), "missing Origin header")

    def test_origin(self):
        server = ServerConnection(origins=["https://example.com"])
        request = self.make_connect_request()
        request.headers["Origin"] = "https://example.com"
        accept = server.accept(Connect(request))

        self.assertIsInstance(accept, Accept)
        self.assertEqual(server.origin, "https://example.com")

    def test_unexpected_origin(self):
        server = ServerConnection(origins=["https://example.com"])
        request = self.make_connect_request()
        request.headers["Origin"] = "https://other.example.com"
        reject = server.accept(Connect(request))

        self.assertIsInstance(reject, Reject)
        self.assertEqual(reject.response.status_code, 403)
        with self.assertRaises(InvalidOrigin) as raised:
            raise reject.exception
        self.assertEqual(
            str(raised.exception), "invalid Origin header: https://other.example.com"
        )

    def test_multiple_origin(self):
        server = ServerConnection(
            origins=["https://example.com", "https://other.example.com"]
        )
        request = self.make_connect_request()
        request.headers["Origin"] = "https://example.com"
        request.headers["Origin"] = "https://other.example.com"
        reject = server.accept(Connect(request))

        self.assertIsInstance(reject, Reject)
        # This is prohibited by the HTTP specification, so the return code is
        # 400 Bad Request rather than 403 Forbidden.
        self.assertEqual(reject.response.status_code, 400)
        with self.assertRaises(InvalidHeader) as raised:
            raise reject.exception
        self.assertEqual(
            str(raised.exception),
            "invalid Origin header: more than one Origin header found",
        )

    def test_supported_origin(self):
        server = ServerConnection(
            origins=["https://example.com", "https://other.example.com"]
        )
        request = self.make_connect_request()
        request.headers["Origin"] = "https://other.example.com"
        accept = server.accept(Connect(request))

        self.assertIsInstance(accept, Accept)
        self.assertEqual(server.origin, "https://other.example.com")

    def test_unsupported_origin(self):
        server = ServerConnection(
            origins=["https://example.com", "https://other.example.com"]
        )
        request = self.make_connect_request()
        request.headers["Origin"] = "https://original.example.com"
        reject = server.accept(Connect(request))

        self.assertIsInstance(reject, Reject)
        self.assertEqual(reject.response.status_code, 403)
        with self.assertRaises(InvalidOrigin) as raised:
            raise reject.exception
        self.assertEqual(
            str(raised.exception), "invalid Origin header: https://original.example.com"
        )

    def test_no_origin_accepted(self):
        server = ServerConnection(origins=[None])
        request = self.make_connect_request()
        accept = server.accept(Connect(request))

        self.assertIsInstance(accept, Accept)
        self.assertIsNone(server.origin)

    def test_no_extensions(self):
        server = ServerConnection()
        request = self.make_connect_request()
        accept = server.accept(Connect(request))

        self.assertIsInstance(accept, Accept)
        self.assertNotIn("Sec-WebSocket-Extensions", accept.response.headers)
        self.assertEqual(server.extensions, [])

    def test_no_extension(self):
        server = ServerConnection(extensions=[ServerOpExtensionFactory()])
        request = self.make_connect_request()
        accept = server.accept(Connect(request))

        self.assertIsInstance(accept, Accept)
        self.assertNotIn("Sec-WebSocket-Extensions", accept.response.headers)
        self.assertEqual(server.extensions, [])

    def test_extension(self):
        server = ServerConnection(extensions=[ServerOpExtensionFactory()])
        request = self.make_connect_request()
        request.headers["Sec-WebSocket-Extensions"] = "x-op; op"
        accept = server.accept(Connect(request))

        self.assertIsInstance(accept, Accept)
        self.assertEqual(
            accept.response.headers["Sec-WebSocket-Extensions"], "x-op; op"
        )
        self.assertEqual(server.extensions, [OpExtension()])

    def test_unexpected_extension(self):
        server = ServerConnection()
        request = self.make_connect_request()
        request.headers["Sec-WebSocket-Extensions"] = "x-op; op"
        accept = server.accept(Connect(request))

        self.assertIsInstance(accept, Accept)
        self.assertNotIn("Sec-WebSocket-Extensions", accept.response.headers)
        self.assertEqual(server.extensions, [])

    def test_unsupported_extension(self):
        server = ServerConnection(extensions=[ServerRsv2ExtensionFactory()])
        request = self.make_connect_request()
        request.headers["Sec-WebSocket-Extensions"] = "x-op; op"
        accept = server.accept(Connect(request))

        self.assertIsInstance(accept, Accept)
        self.assertNotIn("Sec-WebSocket-Extensions", accept.response.headers)
        self.assertEqual(server.extensions, [])

    def test_supported_extension_parameters(self):
        server = ServerConnection(extensions=[ServerOpExtensionFactory("this")])
        request = self.make_connect_request()
        request.headers["Sec-WebSocket-Extensions"] = "x-op; op=this"
        accept = server.accept(Connect(request))

        self.assertIsInstance(accept, Accept)
        self.assertEqual(
            accept.response.headers["Sec-WebSocket-Extensions"], "x-op; op=this"
        )
        self.assertEqual(server.extensions, [OpExtension("this")])

    def test_unsupported_extension_parameters(self):
        server = ServerConnection(extensions=[ServerOpExtensionFactory("this")])
        request = self.make_connect_request()
        request.headers["Sec-WebSocket-Extensions"] = "x-op; op=that"
        accept = server.accept(Connect(request))

        self.assertIsInstance(accept, Accept)
        self.assertNotIn("Sec-WebSocket-Extensions", accept.response.headers)
        self.assertEqual(server.extensions, [])

    def test_multiple_supported_extension_parameters(self):
        server = ServerConnection(
            extensions=[
                ServerOpExtensionFactory("this"),
                ServerOpExtensionFactory("that"),
            ]
        )
        request = self.make_connect_request()
        request.headers["Sec-WebSocket-Extensions"] = "x-op; op=that"
        accept = server.accept(Connect(request))

        self.assertIsInstance(accept, Accept)
        self.assertEqual(
            accept.response.headers["Sec-WebSocket-Extensions"], "x-op; op=that"
        )
        self.assertEqual(server.extensions, [OpExtension("that")])

    def test_multiple_extensions(self):
        server = ServerConnection(
            extensions=[ServerOpExtensionFactory(), ServerRsv2ExtensionFactory()]
        )
        request = self.make_connect_request()
        request.headers["Sec-WebSocket-Extensions"] = "x-op; op"
        request.headers["Sec-WebSocket-Extensions"] = "x-rsv2"
        accept = server.accept(Connect(request))

        self.assertIsInstance(accept, Accept)
        self.assertEqual(
            accept.response.headers["Sec-WebSocket-Extensions"], "x-op; op, x-rsv2"
        )
        self.assertEqual(server.extensions, [OpExtension(), Rsv2Extension()])

    def test_multiple_extensions_order(self):
        server = ServerConnection(
            extensions=[ServerOpExtensionFactory(), ServerRsv2ExtensionFactory()]
        )
        request = self.make_connect_request()
        request.headers["Sec-WebSocket-Extensions"] = "x-rsv2"
        request.headers["Sec-WebSocket-Extensions"] = "x-op; op"
        accept = server.accept(Connect(request))

        self.assertIsInstance(accept, Accept)
        self.assertEqual(
            accept.response.headers["Sec-WebSocket-Extensions"], "x-rsv2, x-op; op"
        )
        self.assertEqual(server.extensions, [Rsv2Extension(), OpExtension()])

    def test_no_subprotocols(self):
        server = ServerConnection()
        request = self.make_connect_request()
        accept = server.accept(Connect(request))

        self.assertIsInstance(accept, Accept)
        self.assertNotIn("Sec-WebSocket-Protocol", accept.response.headers)
        self.assertIsNone(server.subprotocol)

    def test_no_subprotocol(self):
        server = ServerConnection(subprotocols=["chat"])
        request = self.make_connect_request()
        accept = server.accept(Connect(request))

        self.assertIsInstance(accept, Accept)
        self.assertNotIn("Sec-WebSocket-Protocol", accept.response.headers)
        self.assertIsNone(server.subprotocol)

    def test_subprotocol(self):
        server = ServerConnection(subprotocols=["chat"])
        request = self.make_connect_request()
        request.headers["Sec-WebSocket-Protocol"] = "chat"
        accept = server.accept(Connect(request))

        self.assertIsInstance(accept, Accept)
        self.assertEqual(accept.response.headers["Sec-WebSocket-Protocol"], "chat")
        self.assertEqual(server.subprotocol, "chat")

    def test_unexpected_subprotocol(self):
        server = ServerConnection()
        request = self.make_connect_request()
        request.headers["Sec-WebSocket-Protocol"] = "chat"
        accept = server.accept(Connect(request))

        self.assertIsInstance(accept, Accept)
        self.assertNotIn("Sec-WebSocket-Protocol", accept.response.headers)
        self.assertIsNone(server.subprotocol)

    def test_multiple_subprotocols(self):
        server = ServerConnection(subprotocols=["superchat", "chat"])
        request = self.make_connect_request()
        request.headers["Sec-WebSocket-Protocol"] = "superchat"
        request.headers["Sec-WebSocket-Protocol"] = "chat"
        accept = server.accept(Connect(request))

        self.assertIsInstance(accept, Accept)
        self.assertEqual(accept.response.headers["Sec-WebSocket-Protocol"], "superchat")
        self.assertEqual(server.subprotocol, "superchat")

    def test_supported_subprotocol(self):
        server = ServerConnection(subprotocols=["superchat", "chat"])
        request = self.make_connect_request()
        request.headers["Sec-WebSocket-Protocol"] = "chat"
        accept = server.accept(Connect(request))

        self.assertIsInstance(accept, Accept)
        self.assertEqual(accept.response.headers["Sec-WebSocket-Protocol"], "chat")
        self.assertEqual(server.subprotocol, "chat")

    def test_unsupported_subprotocol(self):
        server = ServerConnection(subprotocols=["superchat", "chat"])
        request = self.make_connect_request()
        request.headers["Sec-WebSocket-Protocol"] = "otherchat"
        accept = server.accept(Connect(request))

        self.assertIsInstance(accept, Accept)
        self.assertNotIn("Sec-WebSocket-Protocol", accept.response.headers)
        self.assertIsNone(server.subprotocol)

    def test_extra_headers(self):
        for extra_headers in [
            Headers({"X-Spam": "Eggs"}),
            {"X-Spam": "Eggs"},
            [("X-Spam", "Eggs")],
            lambda path, headers: Headers({"X-Spam": "Eggs"}),
            lambda path, headers: {"X-Spam": "Eggs"},
            lambda path, headers: [("X-Spam", "Eggs")],
        ]:
            with self.subTest(extra_headers=extra_headers):
                server = ServerConnection(extra_headers=extra_headers)
                request = self.make_connect_request()
                accept = server.accept(Connect(request))

                self.assertIsInstance(accept, Accept)
                self.assertEqual(accept.response.headers["X-Spam"], "Eggs")

    def test_extra_headers_overrides_server(self):
        server = ServerConnection(extra_headers={"Server": "Other"})
        request = self.make_connect_request()
        accept = server.accept(Connect(request))

        self.assertIsInstance(accept, Accept)
        self.assertEqual(accept.response.headers["Server"], "Other")
