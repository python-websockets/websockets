"""
:mod:`websockets.legacy.auth` provides HTTP Basic Authentication according to
:rfc:`7235` and :rfc:`7617`.

"""


import functools
import hmac
import http
from typing import Any, Awaitable, Callable, Iterable, Optional, Tuple, Union, cast

from ..datastructures import Headers
from ..exceptions import InvalidHeader
from ..headers import build_www_authenticate_basic, parse_authorization_basic
from .server import HTTPResponse, WebSocketServerProtocol


__all__ = ["BasicAuthWebSocketServerProtocol", "basic_auth_protocol_factory"]

Credentials = Tuple[str, str]


def is_credentials(value: Any) -> bool:
    try:
        username, password = value
    except (TypeError, ValueError):
        return False
    else:
        return isinstance(username, str) and isinstance(password, str)


class BasicAuthWebSocketServerProtocol(WebSocketServerProtocol):
    """
    WebSocket server protocol that enforces HTTP Basic Auth.

    """

    realm = ""

    def __init__(
        self,
        *args: Any,
        realm: Optional[str] = None,
        check_credentials: Optional[Callable[[str, str], Awaitable[bool]]] = None,
        **kwargs: Any,
    ) -> None:
        if realm is not None:
            self.realm = realm  # shadow class attribute
        self._check_credentials = check_credentials
        super().__init__(*args, **kwargs)

    async def check_credentials(self, username: str, password: str) -> bool:
        """
        Check whether credentials are authorized.

        If ``check_credentials`` returns ``True``, the WebSocket handshake
        continues. If it returns ``False``, the handshake fails with a HTTP
        401 error.

        This coroutine may be overridden in a subclass, for example to
        authenticate against a database or an external service.

        """
        if self._check_credentials is not None:
            return await self._check_credentials(username, password)

        return False

    async def process_request(
        self,
        path: str,
        request_headers: Headers,
    ) -> Optional[HTTPResponse]:
        """
        Check HTTP Basic Auth and return a HTTP 401 response if needed.

        """
        try:
            authorization = request_headers["Authorization"]
        except KeyError:
            return (
                http.HTTPStatus.UNAUTHORIZED,
                [("WWW-Authenticate", build_www_authenticate_basic(self.realm))],
                b"Missing credentials\n",
            )

        try:
            username, password = parse_authorization_basic(authorization)
        except InvalidHeader:
            return (
                http.HTTPStatus.UNAUTHORIZED,
                [("WWW-Authenticate", build_www_authenticate_basic(self.realm))],
                b"Unsupported credentials\n",
            )

        if not await self.check_credentials(username, password):
            return (
                http.HTTPStatus.UNAUTHORIZED,
                [("WWW-Authenticate", build_www_authenticate_basic(self.realm))],
                b"Invalid credentials\n",
            )

        self.username = username

        return await super().process_request(path, request_headers)


def basic_auth_protocol_factory(
    realm: Optional[str] = None,
    credentials: Optional[Union[Credentials, Iterable[Credentials]]] = None,
    check_credentials: Optional[Callable[[str, str], Awaitable[bool]]] = None,
    create_protocol: Optional[Callable[[Any], BasicAuthWebSocketServerProtocol]] = None,
) -> Callable[[Any], BasicAuthWebSocketServerProtocol]:
    """
    Protocol factory that enforces HTTP Basic Auth.

    ``basic_auth_protocol_factory`` is designed to integrate with
    :func:`~websockets.legacy.server.serve` like this::

        websockets.serve(
            ...,
            create_protocol=websockets.basic_auth_protocol_factory(
                realm="my dev server",
                credentials=("hello", "iloveyou"),
            )
        )

    ``realm`` indicates the scope of protection. It should contain only ASCII
    characters because the encoding of non-ASCII characters is undefined.
    Refer to section 2.2 of :rfc:`7235` for details.

    ``credentials`` defines hard coded authorized credentials. It can be a
    ``(username, password)`` pair or a list of such pairs.

    ``check_credentials`` defines a coroutine that checks whether credentials
    are authorized. This coroutine receives ``username`` and ``password``
    arguments and returns a :class:`bool`.

    One of ``credentials`` or ``check_credentials`` must be provided but not
    both.

    By default, ``basic_auth_protocol_factory`` creates a factory for building
    :class:`BasicAuthWebSocketServerProtocol` instances. You can override this
    with the ``create_protocol`` parameter.

    :param realm: scope of protection
    :param credentials: hard coded credentials
    :param check_credentials: coroutine that verifies credentials
    :raises TypeError: if the credentials argument has the wrong type

    """
    if (credentials is None) == (check_credentials is None):
        raise TypeError("provide either credentials or check_credentials")

    if credentials is not None:
        if is_credentials(credentials):
            credentials_list = [cast(Credentials, credentials)]
        elif isinstance(credentials, Iterable):
            credentials_list = list(credentials)
            if not all(is_credentials(item) for item in credentials_list):
                raise TypeError(f"invalid credentials argument: {credentials}")
        else:
            raise TypeError(f"invalid credentials argument: {credentials}")

        credentials_dict = dict(credentials_list)

        async def check_credentials(username: str, password: str) -> bool:
            try:
                expected_password = credentials_dict[username]
            except KeyError:
                return False
            return hmac.compare_digest(expected_password, password)

    if create_protocol is None:
        # Not sure why mypy cannot figure this out.
        create_protocol = cast(
            Callable[[Any], BasicAuthWebSocketServerProtocol],
            BasicAuthWebSocketServerProtocol,
        )

    return functools.partial(
        create_protocol,
        realm=realm,
        check_credentials=check_credentials,
    )
