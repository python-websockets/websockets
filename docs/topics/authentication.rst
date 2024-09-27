Authentication
==============

The WebSocket protocol is designed for creating web applications that require
bidirectional communication between browsers and servers.

In most practical use cases, WebSocket servers need to authenticate clients in
order to route communications appropriately and securely.

:rfc:`6455` remains elusive when it comes to authentication:

    This protocol doesn't prescribe any particular way that servers can
    authenticate clients during the WebSocket handshake. The WebSocket
    server can use any client authentication mechanism available to a
    generic HTTP server, such as cookies, HTTP authentication, or TLS
    authentication.

None of these three mechanisms works well in practice. Using cookies is
cumbersome, HTTP authentication isn't supported by all mainstream browsers,
and TLS authentication in a browser is an esoteric user experience.

Fortunately, there are better alternatives! Let's discuss them.

System design
-------------

Consider a setup where the WebSocket server is separate from the HTTP server.

Most servers built with websockets adopt this design because they're a component
in a web application and websockets doesn't aim at supporting HTTP.

The following diagram illustrates the authentication flow.

.. image:: authentication.svg

Assuming the current user is authenticated with the HTTP server (1), the
application needs to obtain credentials from the HTTP server (2) in order to
send them to the WebSocket server (3), who can check them against the database
of user accounts (4).

Usernames and passwords aren't a good choice of credentials here, if only
because passwords aren't available in clear text in the database.

Tokens linked to user accounts are a better choice. These tokens must be
impossible to forge by an attacker. For additional security, they can be
short-lived or even single-use.

Sending credentials
-------------------

Assume the web application obtained authentication credentials, likely a
token, from the HTTP server. There's four options for passing them to the
WebSocket server.

1. **Sending credentials as the first message in the WebSocket connection.**

   This is fully reliable and the most secure mechanism in this discussion. It
   has two minor downsides:

   * Authentication is performed at the application layer. Ideally, it would
     be managed at the protocol layer.

   * Authentication is performed after the WebSocket handshake, making it
     impossible to monitor authentication failures with HTTP response codes.

2. **Adding credentials to the WebSocket URI in a query parameter.**

   This is also fully reliable but less secure. Indeed, it has a major
   downside:

   * URIs end up in logs, which leaks credentials. Even if that risk could be
     lowered with single-use tokens, it is usually considered unacceptable.

   Authentication is still performed at the application layer but it can
   happen before the WebSocket handshake, which improves separation of
   concerns and enables responding to authentication failures with HTTP 401.

3. **Setting a cookie on the domain of the WebSocket URI.**

   Cookies are undoubtedly the most common and hardened mechanism for sending
   credentials from a web application to a server. In an HTTP application,
   credentials would be a session identifier or a serialized, signed session.

   Unfortunately, when the WebSocket server runs on a different domain from
   the web application, this idea hits the wall of the `Same-Origin Policy`_.
   For security reasons, setting a cookie on a different origin is impossible.

   The proper workaround consists in:

   * creating a hidden iframe_ served from the domain of the WebSocket server
   * sending the token to the iframe with postMessage_
   * setting the cookie in the iframe

   before opening the WebSocket connection.

   Sharing a parent domain (e.g. example.com) between the HTTP server (e.g.
   www.example.com) and the WebSocket server (e.g. ws.example.com) and setting
   the cookie on that parent domain would work too.

   However, the cookie would be shared with all subdomains of the parent
   domain. For a cookie containing credentials, this is unacceptable.

.. _Same-Origin Policy: https://developer.mozilla.org/en-US/docs/Web/Security/Same-origin_policy
.. _iframe: https://developer.mozilla.org/en-US/docs/Web/HTML/Element/iframe
.. _postMessage: https://developer.mozilla.org/en-US/docs/Web/API/MessagePort/postMessage

4. **Adding credentials to the WebSocket URI in user information.**

   Letting the browser perform HTTP Basic Auth is a nice idea in theory.

   In practice it doesn't work due to browser support limitations:

   * Chrome behaves as expected.

   * Firefox caches credentials too aggressively.

     When connecting again to the same server with new credentials, it reuses
     the old credentials, which may be expired, resulting in an HTTP 401. Then
     the next connection succeeds. Perhaps errors clear the cache.

     When tokens are short-lived or single-use, this bug produces an
     interesting effect: every other WebSocket connection fails.

   * Safari behaves as expected.

Two other options are off the table:

1. **Setting a custom HTTP header**

   This would be the most elegant mechanism, solving all issues with the options
   discussed above.

   Unfortunately, it doesn't work because the `WebSocket API`_ doesn't support
   `setting custom headers`_.

.. _WebSocket API: https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API
.. _setting custom headers: https://github.com/whatwg/html/issues/3062

2. **Authenticating with a TLS certificate**

   While this is suggested by the RFC, installing a TLS certificate is too far
   from the mainstream experience of browser users. This could make sense in
   high security contexts.

   I hope that developers working on projects in this category don't take
   security advice from the documentation of random open source projects :-)

Let's experiment!
-----------------

The `experiments/authentication`_ directory demonstrates these techniques.

Run the experiment in an environment where websockets is installed:

.. _experiments/authentication: https://github.com/python-websockets/websockets/tree/main/experiments/authentication

.. code-block:: console

    $ python experiments/authentication/app.py
    Running on http://localhost:8000/

When you browse to the HTTP server at http://localhost:8000/ and you submit a
username, the server creates a token and returns a testing web page.

This page opens WebSocket connections to four WebSocket servers running on
four different origins. It attempts to authenticate with the token in four
different ways.

First message
.............

As soon as the connection is open, the client sends a message containing the
token:

.. code-block:: javascript

    const websocket = new WebSocket("ws://.../");
    websocket.onopen = () => websocket.send(token);

    // ...

At the beginning of the connection handler, the server receives this message
and authenticates the user. If authentication fails, the server closes the
connection:

.. code-block:: python

    from websockets.frames import CloseCode

    async def first_message_handler(websocket):
        token = await websocket.recv()
        user = get_user(token)
        if user is None:
            await websocket.close(CloseCode.INTERNAL_ERROR, "authentication failed")
            return

        ...

Query parameter
...............

The client adds the token to the WebSocket URI in a query parameter before
opening the connection:

.. code-block:: javascript

    const uri = `ws://.../?token=${token}`;
    const websocket = new WebSocket(uri);

    // ...

The server intercepts the HTTP request, extracts the token and authenticates
the user. If authentication fails, it returns an HTTP 401:

.. code-block:: python

    async def query_param_auth(connection, request):
        token = get_query_param(request.path, "token")
        if token is None:
            return connection.respond(http.HTTPStatus.UNAUTHORIZED, "Missing token\n")

        user = get_user(token)
        if user is None:
            return connection.respond(http.HTTPStatus.UNAUTHORIZED, "Invalid token\n")

        connection.username = user

Cookie
......

The client sets a cookie containing the token before opening the connection.

The cookie must be set by an iframe loaded from the same origin as the
WebSocket server. This requires passing the token to this iframe.

.. code-block:: javascript

    // in main window
    iframe.contentWindow.postMessage(token, "http://...");

    // in iframe
    document.cookie = `token=${data}; SameSite=Strict`;

    // in main window
    const websocket = new WebSocket("ws://.../");

    // ...

This sequence must be synchronized between the main window and the iframe.
This involves several events. Look at the full implementation for details.

The server intercepts the HTTP request, extracts the token and authenticates
the user. If authentication fails, it returns an HTTP 401:

.. code-block:: python

    async def cookie_auth(connection, request):
        # Serve iframe on non-WebSocket requests
        ...

        token = get_cookie(request.headers.get("Cookie", ""), "token")
        if token is None:
            return connection.respond(http.HTTPStatus.UNAUTHORIZED, "Missing token\n")

        user = get_user(token)
        if user is None:
            return connection.respond(http.HTTPStatus.UNAUTHORIZED, "Invalid token\n")

        connection.username = user

User information
................

The client adds the token to the WebSocket URI in user information before
opening the connection:

.. code-block:: javascript

    const uri = `ws://token:${token}@.../`;
    const websocket = new WebSocket(uri);

    // ...

Since HTTP Basic Auth is designed to accept a username and a password rather
than a token, we send ``token`` as username and the token as password.

The server intercepts the HTTP request, extracts the token and authenticates
the user. If authentication fails, it returns an HTTP 401:

.. code-block:: python

    from websockets.asyncio.server import basic_auth as websockets_basic_auth

    def check_credentials(username, password):
        return username == get_user(password)

    basic_auth = websockets_basic_auth(check_credentials=check_credentials)

Machine-to-machine authentication
---------------------------------

When the WebSocket client is a standalone program rather than a script running
in a browser, there are far fewer constraints. HTTP Authentication is the best
solution in this scenario.

To authenticate a websockets client with HTTP Basic Authentication
(:rfc:`7617`), include the credentials in the URI:

.. code-block:: python

    from websockets.asyncio.client import connect

    async with connect(f"wss://{username}:{password}@.../") as websocket:
        ...

(You must :func:`~urllib.parse.quote` ``username`` and ``password`` if they
contain unsafe characters.)

To authenticate a websockets client with HTTP Bearer Authentication
(:rfc:`6750`), add a suitable ``Authorization`` header:

.. code-block:: python

    from websockets.asyncio.client import connect

    headers = {"Authorization": f"Bearer {token}"}
    async with connect("wss://.../", additional_headers=headers) as websocket:
        ...
