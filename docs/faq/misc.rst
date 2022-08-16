Miscellaneous
=============

.. currentmodule:: websockets

Can I use websockets without ``async`` and ``await``?
.....................................................

No, there is no convenient way to do this. You should use another library.

Are there ``onopen``, ``onmessage``, ``onerror``, and ``onclose`` callbacks?
............................................................................

No, there aren't.

websockets provides high-level, coroutine-based APIs. Compared to callbacks,
coroutines make it easier to manage control flow in concurrent code.

If you prefer callback-based APIs, you should use another library.

Why do I get the error: ``module 'websockets' has no attribute '...'``?
.......................................................................

Often, this is because you created a script called ``websockets.py`` in your
current working directory. Then ``import websockets`` imports this module
instead of the websockets library.
