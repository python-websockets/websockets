websockets
==========

|licence| |version| |pyversions| |tests| |docs| |openssf|

.. |licence| image:: https://img.shields.io/pypi/l/websockets.svg
    :target: https://pypi.python.org/pypi/websockets

.. |version| image:: https://img.shields.io/pypi/v/websockets.svg
    :target: https://pypi.python.org/pypi/websockets

.. |pyversions| image:: https://img.shields.io/pypi/pyversions/websockets.svg
    :target: https://pypi.python.org/pypi/websockets

.. |tests| image:: https://img.shields.io/github/checks-status/python-websockets/websockets/main?label=tests
   :target: https://github.com/python-websockets/websockets/actions/workflows/tests.yml

.. |docs| image:: https://img.shields.io/readthedocs/websockets.svg
   :target: https://websockets.readthedocs.io/

.. |openssf| image:: https://bestpractices.coreinfrastructure.org/projects/6475/badge
   :target: https://bestpractices.coreinfrastructure.org/projects/6475

websockets is a library for building WebSocket_ servers and clients in Python
with a focus on correctness, simplicity, robustness, and performance.

.. _WebSocket: https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API

It supports several network I/O and control flow paradigms.

1. The default implementation builds upon :mod:`asyncio`, Python's built-in
   asynchronous I/O library. It provides an elegant coroutine-based API. It's
   ideal for servers that handle many client connections.

2. The :mod:`threading` implementation is a good alternative for clients,
   especially if you aren't familiar with :mod:`asyncio`. It may also be used
   for servers that handle few client connections.

3. The `Sans-I/O`_ implementation is designed for integrating in third-party
   libraries, typically application servers, in addition being used internally
   by websockets.

.. _Sans-I/O: https://sans-io.readthedocs.io/

Refer to the :doc:`feature support matrices <reference/features>` for the full
list of features provided by each implementation.

.. admonition:: The :mod:`asyncio` implementation was rewritten.
   :class: tip

   The new implementation in ``websockets.asyncio`` builds upon the Sans-I/O
   implementation. It adds features that were impossible to provide in the
   original design. It was introduced in version 13.0.

   The historical implementation in ``websockets.legacy`` traces its roots to
   early versions of websockets. While it's stable and robust, it was deprecated
   in version 14.0 and it will be removed by 2030.

   The new implementation provides the same features as the historical
   implementation, and then some. If you're using the historical implementation,
   you should :doc:`ugrade to the new implementation <howto/upgrade>`.

Here's an echo server and corresponding client.

.. tab:: asyncio

    .. literalinclude:: ../example/asyncio/echo.py

.. tab:: threading

    .. literalinclude:: ../example/sync/echo.py

.. tab:: asyncio
    :new-set:

    .. literalinclude:: ../example/asyncio/hello.py

.. tab:: threading

    .. literalinclude:: ../example/sync/hello.py

Don't worry about the opening and closing handshakes, pings and pongs, or any
other behavior described in the WebSocket specification. websockets takes care
of this under the hood so you can focus on your application!

Also, websockets provides an interactive client:

.. code-block:: console

    $ python -m websockets ws://localhost:8765/
    Connected to ws://localhost:8765/.
    > Hello world!
    < Hello world!
    Connection closed: 1000 (OK).

Do you like it? :doc:`Let's dive in! <intro/index>`

.. toctree::
   :hidden:

   intro/index
   howto/index
   faq/index
   reference/index
   topics/index
   project/index
