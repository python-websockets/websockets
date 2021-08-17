websockets
==========

|licence| |version| |pyversions| |wheel| |tests| |docs|

.. |licence| image:: https://img.shields.io/pypi/l/websockets.svg
    :target: https://pypi.python.org/pypi/websockets

.. |version| image:: https://img.shields.io/pypi/v/websockets.svg
    :target: https://pypi.python.org/pypi/websockets

.. |pyversions| image:: https://img.shields.io/pypi/pyversions/websockets.svg
    :target: https://pypi.python.org/pypi/websockets

.. |wheel| image:: https://img.shields.io/pypi/wheel/websockets.svg
    :target: https://pypi.python.org/pypi/websockets

.. |tests| image:: https://img.shields.io/github/checks-status/aaugustin/websockets/main
   :target: https://github.com/aaugustin/websockets/actions/workflows/tests.yml

.. |docs| image:: https://img.shields.io/readthedocs/websockets.svg
   :target: https://websockets.readthedocs.io/

websockets is a library for building WebSocket servers_ and clients_ in Python
with a focus on correctness and simplicity.

.. _servers: https://github.com/aaugustin/websockets/blob/main/example/server.py
.. _clients: https://github.com/aaugustin/websockets/blob/main/example/client.py

Built on top of :mod:`asyncio`, Python's standard asynchronous I/O framework,
it provides an elegant coroutine-based API.

Here's how a client sends and receives messages:

.. literalinclude:: ../example/hello.py

And here's an echo server:

.. literalinclude:: ../example/echo.py

Do you like it? Let's dive in!

.. toctree::
   :hidden:

   intro/index
   howto/index
   reference/index
   topics/index
   project/index
