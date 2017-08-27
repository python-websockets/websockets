WebSockets |pypi| |circleci| |codecov|
======================================

``websockets`` is a library for developing WebSocket servers_ and clients_ in
Python. It implements `RFC 6455`_ and `RFC 7692`_ with a focus on correctness
and simplicity. It passes the `Autobahn Testsuite`_.

Built on top of Python's asynchronous I/O support introduced in `PEP 3156`_,
it provides an API based on coroutines, making it easy to write highly
concurrent applications.

Installation is as simple as ``pip install websockets``. It requires Python ≥
3.4 or Python 3.3 with the ``asyncio`` module, which is available with ``pip
install asyncio``.

Documentation is available on `Read the Docs`_.

Bug reports, patches and suggestions welcome! Just open an issue_ or send a
`pull request`_.

.. _servers: https://github.com/aaugustin/websockets/blob/master/example/server.py
.. _clients: https://github.com/aaugustin/websockets/blob/master/example/client.py
.. _RFC 6455: http://tools.ietf.org/html/rfc6455
.. _RFC 7692: http://tools.ietf.org/html/rfc7692
.. _Autobahn Testsuite: https://github.com/aaugustin/websockets/blob/master/compliance/README.rst
.. _PEP 3156: http://www.python.org/dev/peps/pep-3156/
.. _Read the Docs: https://websockets.readthedocs.io/
.. _issue: https://github.com/aaugustin/websockets/issues/new
.. _pull request: https://github.com/aaugustin/websockets/compare/

.. |pypi| image:: https://img.shields.io/pypi/v/websockets.svg
  :target: https://pypi.python.org/pypi/websockets
.. |circleci| image:: https://circleci.com/gh/aaugustin/websockets/tree/master.svg?style=shield
    :target: https://circleci.com/gh/aaugustin/websockets/tree/master
.. |codecov| image:: https://codecov.io/gh/aaugustin/websockets/branch/master/graph/badge.svg
  :target: https://codecov.io/gh/aaugustin/websockets
