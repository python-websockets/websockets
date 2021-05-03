Using websockets with Django
============================

If you're looking at adding real-time capabilities to a Django project with
WebSocket, you have two main options.

1. Using Django Channels_, a project adding WebSocket to Django, among other
   features. This approach is fully supported by Django. However, it requires
   switching to a new deployment architecture.

2. Deploying a separate WebSocket server next to your Django project. This
   technique is well suited when you need to add a small set of real-time
   features — maybe a notification service — to a HTTP application.

.. _Channels: https://channels.readthedocs.io/en/latest/

This guide shows how to implement the second technique with websockets. It
assumes familiarity with Django.

Authenticating connections
--------------------------

Since the websockets server will run outside of Django, we need to connect it
to ``django.contrib.auth``.

Our clients are running in browser. The `WebSocket API`_ doesn't support
setting `custom headers`_ so our options boil down to:

* HTTP Basic Auth: this seems technically possible but isn't supported by
  Firefox (`bug 1229443`_) so browser support is clearly insufficient.
* Sharing cookies: this is technically possible if there's a common parent
  domain between the Django server (e.g. api.example.com) and the websockets
  server (e.g. ws.example.com). However, there's a risk to share cookies too
  widely (e.g. with anything under .example.com here). For authentication
  cookies, this risk seems unacceptable.
* Sending an authentication ticket: Django generates a secure single-use token
  with the user ID. The browser includes this token in the WebSocket URI when
  it connects to the server in order to authenticate. It could also send the
  ticket over the WebSocket connection in the first message, however this is a
  bit more difficult to monitor, as you can't detect authentication failures
  simply by looking at HTTP response codes.

.. _custom headers: https://github.com/whatwg/html/issues/3062
.. _WebSocket API: https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API
.. _bug 1229443: https://bugzilla.mozilla.org/show_bug.cgi?id=1229443

To generate our authentication tokens, we'll use `django-sesame`_, a small
library designed exactly for this purpose.

 .. _django-sesame: https://github.com/aaugustin/django-sesame

Add django-sesame to the dependencies of your Django project, install it and configure it in the settings of the project:

.. code:: python

    AUTHENTICATION_BACKENDS = [
        "django.contrib.auth.backends.ModelBackend",
        "sesame.backends.ModelBackend",
    ]

(If your project already uses another authentication backend than the default
``"django.contrib.auth.backends.ModelBackend"``, adjust accordingly.)

You don't need ``"sesame.middleware.AuthenticationMiddleware"``. It is for
authenticating users in the Django server, while we're authenticating them in
the websockets server.

We'd like our tokens to be valid for 30 seconds and usable only once. A
shorter lifespan is possible but it would make manual testing difficult.

Configure django-sesame accordingly in the settings of your Django project:

.. code:: python

    SESAME_MAX_AGE = 30
    SESAME_ONE_TIME = True

Now you can generate tokens in a ``django-admin shell`` as follows:

.. code:: pycon

    >>> from django.contrib.auth import get_user_model
    >>> User = get_user_model()
    >>> user = User.objects.get(username="<your username>")
    >>> from sesame.utils import get_token
    >>> get_token(user)
    '<your token>'

Keep this console open: since tokens are single use, we'll have to generate a
new token every time we want to test our server.

Let's move on to the websockets server. Add websockets to the dependencies of
your Django project and install it.

Now here's a way to implement authentication. We're taking advantage of the
:meth:`~websockets.server.WebSocketServerProtocol.process_request` hook to
authenticate requests. If authentication succeeds, we store the user as an
attribute of the connection in order to make it available to the connection
handler. If authentication fails, we return a HTTP 401 Unauthorized error.

.. literalinclude:: ../../example/django/authentication.py

Let's unpack this code.

We're using Django in a `standalone script`_. This requires setting the
``DJANGO_SETTINGS_MODULE`` environment variable and calling ``django.setup()``
before doing anything with Django.

.. _standalone script: https://docs.djangoproject.com/en/stable/topics/settings/#calling-django-setup-is-required-for-standalone-django-usage

We subclass :class:`~websockets.server.WebSocketServerProtocol` and override
:meth:`~websockets.server.WebSocketServerProtocol.process_request`, where:

* We extract the token from the URL with the ``get_sesame()`` utility function
  defined just above. If the token is missing, we return a HTTP 401 error.
* We authenticate the user with ``get_user()``, the API for `authentication
  outside views`_. If authentication fails, we return a HTTP 401 error.

.. _authentication outside views: https://github.com/aaugustin/django-sesame#authentication-outside-views

When we call an API that makes a database query, we wrap the call in
:func:`~asyncio.to_thread`. Indeed, the Django ORM doesn't support
asynchronous I/O. We would block the event loop if we didn't run these calls
in a separate thread. :func:`~asyncio.to_thread` is available since Python
3.9; in earlier versions, use :meth:`~asyncio.loop.run_in_executor` instead.

The connection handler accesses the logged-in user that we stored as an
attribute of the connection object so we can test that authentication works.

Finally, we start a server with :func:`~websockets.serve`, with the
``create_protocol`` pointing to our subclass of
:class:`~websockets.server.WebSocketServerProtocol`.

We're ready to test!

Make sure the ``DJANGO_SETTINGS_MODULE`` environment variable is set to the
Python path to your settings module and start the websockets server. If you
saved the server implementation to a file called ``authentication.py``:

.. code:: console

    $ python authentication.py

Open a new shell, generate a new token — remember, they're only valid for
30 seconds — and use it to connect to your server:

.. code:: console

    $ python -m websockets "ws://localhost:8888/?sesame=<your token>"
    Connected to ws://localhost:8888/?sesame=<your token>
    < Hello <your username>!
    Connection closed: code = 1000 (OK), no reason.

It works!

If we try to reuse the same token, the connection is now rejected:

.. code:: console

    $ python -m websockets "ws://localhost:8888/?sesame=<your token>"
    Failed to connect to ws://localhost:8888/?sesame=<your token>:
    server rejected WebSocket connection: HTTP 401.

You can also test from a browser by generating a new token and running the
following code in the JavaScript console of the browser:

.. code:: javascript

    webSocket = new WebSocket("ws://localhost:8888/?sesame=<your token>");
    webSocket.onmessage = (event) => console.log(event.data);

Streaming events
----------------

We can connect and authenticate but our server doesn't do anything useful yet!

Let's send a message every time any user makes any action in the admin. This
message will be broadcast to all users who can access the model on which the
action was made. This may be used for showing notifications to other users.

Many use cases for WebSocket with Django follow a similar pattern.

We need a event bus to enable communications between Django and websockets.
Both sides connect permanently to the bus. Then Django writes events and
websockets reads them. For the sake of simplicity, we'll rely on `Redis
Pub/Sub`_.

.. _Redis Pub/Sub: https://redis.io/topics/pubsub

Let's start by writing events. The easiest way to add Redis to a Django
project is by configuring a cache backend with `django-redis`_. This library
manages connections to Redis efficiently, persisting them between requests,
and provides an API to access the Redis connection directly.

.. _django-redis: https://github.com/jazzband/django-redis

Install Redis, add django-redis to the dependencies of your Django project,
install it and configure it in the settings of the project:

.. code:: python

    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": "redis://127.0.0.1:6379/1",
        },
    }

If you already have a default cache, add a new one with a different name and
change ``get_redis_connection("default")`` in the code below to the same name.

Add the following code to a module that is imported when your Django project
starts. Typically, you would put it in a ``signals.py`` module, which you
would import in the ``AppConfig.ready()`` method of one of your apps:

.. literalinclude:: ../../example/django/signals.py

This code runs every time the admin saves a ``LogEntry`` object to keep track
of a change. It extracts interesting data, serializes it to JSON, and writes
an event to Redis.

Let's check that it works:

.. code:: console

    $ redis-cli
    127.0.0.1:6379> SELECT 1
    OK
    127.0.0.1:6379[1]> SUBSCRIBE events
    Reading messages... (press Ctrl-C to quit)
    1) "subscribe"
    2) "events"
    3) (integer) 1

Leave this command running, start the Django development server and make
changes in the admin: add, modify, or delete objects. You should see
corresponding events published to the ``"events"`` stream.

Now let's turn to reading events and broadcasting them to connected clients.
We'll reuse our custom ``ServerProtocol`` class for authentication. Then we
need to add several features:

* Keep track of connected clients so we can broadcast messages.
* Tell which content types the user has permission to view or to change.
* Connect to the message bus and read events.
* Broadcast these events to users who have corresponding permissions.

Here's a complete implementation.

.. literalinclude:: ../../example/django/notifications.py

Since the ``get_content_types()`` function makes a database query, it is
wrapped inside ``asyncio.to_thread()``. It runs once when each WebSocket
connection is open; then its result is cached for the lifetime of the
connection. Indeed, running it for each message would trigger database queries
for all connected users at the same time, which could hurt the database.

The connection handler merely registers the connection in a global variable,
associated to the list of content types for which events should be sent to
that connection, and waits until the client disconnects.

The ``process_events()`` function reads events from Redis and broadcasts them
to all connections that should receive them. We don't care much if a sending a
notification fails — this happens when a connection drops between the moment
we iterate on connections and the moment the corresponding message is sent —
so we start a task with for each message and forget about it. Also, this means
we're immediately ready to process the next event, even if it takes time to
send a message to a slow client.

Since Redis can publish a message to multiple subscribers, multiple instances
of this server can safely run in parallel.

In theory, given enough servers, this design can scale to a hundred million
clients, since Redis can handle ten thousand servers and each server can
handle ten thousand clients. In practice, you would need a more scalable
message bus before reaching that scale, due to the volume of messages.
