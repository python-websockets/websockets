Miscellaneous
=============

.. currentmodule:: websockets

.. Remove this question when dropping Python < 3.13, which provides natively
.. a good error message in this case.

Why do I get the error: ``module 'websockets' has no attribute '...'``?
.......................................................................

Often, this is because you created a script called ``websockets.py`` in your
current working directory. Then ``import websockets`` imports this module
instead of the websockets library.

Why is websockets slower than another library in my benchmark?
..............................................................

Not all libraries are as feature-complete as websockets. For a fair benchmark,
you should disable features that the other library doesn't provide. Typically,
you must disable:

* Compression: set ``compression=None``
* Keepalive: set ``ping_interval=None``
* Limits: set ``max_size=None``
* UTF-8 decoding: send ``bytes`` rather than ``str``

Then, please consider whether websockets is the bottleneck of the performance
of your application. Usually, in real-world applications, CPU time spent in
websockets is negligible compared to time spent in the application logic.

Are there ``onopen``, ``onmessage``, ``onerror``, and ``onclose`` callbacks?
............................................................................

No, there aren't.

websockets provides high-level, coroutine-based APIs. Compared to callbacks,
coroutines make it easier to manage control flow in concurrent code.

If you prefer callback-based APIs, you should use another library.
