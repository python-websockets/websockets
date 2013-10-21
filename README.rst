README
======

``websockets`` is an implementation of `RFC 6455`_, the WebSocket protocol,
with a focus on simplicity and correctness.

It's built on top on Python's asynchronous I/O features described in `PEP
3156`_.

It requires Python ≥ 3.4 or Python 3.3 with a copy of the ``asyncio`` module
available in the `Tulip`_ repository.

It passes the `Autobahn Testsuite`_.

.. _RFC 6455: http://tools.ietf.org/html/rfc6455
.. _PEP 3156: http://www.python.org/dev/peps/pep-3156/
.. _Tulip: http://code.google.com/p/tulip/
.. _Autobahn Testsuite: https://github.com/aaugustin/websockets/blob/master/compliance/README.rst

The documentation is available at http://aaugustin.github.io/websockets/.
