WebSockets
==========

``websockets`` is a library for developing WebSocket servers_ and clients_ in
Python. It implements `RFC 6455`_ and `RFC 7692`_ with a focus on correctness
and simplicity. It passes the `Autobahn Testsuite`_.

Built on top of :mod:`asyncio`, Python's standard asynchronous I/O framework,
it provides a straightforward API based on coroutines, making it easy to write
highly concurrent applications.

Installation
------------

Installation is as simple as ``pip install websockets``.

It requires Python ≥ 3.4.

User guide
----------

If you're new to ``websockets``, :doc:`intro` describes usage patterns and
provides examples.

If you've used ``websockets`` before and just need a quick reference, have a
look at :doc:`cheatsheet`.

If you need more details, the :doc:`api` documentation is for you.

If you're upgrading ``websockets``, check the :doc:`changelog`.

Contributing
------------

Bug reports, patches and suggestions welcome! Just open an issue_ or send a
`pull request`_.

.. _servers: https://github.com/aaugustin/websockets/blob/master/example/server.py
.. _clients: https://github.com/aaugustin/websockets/blob/master/example/client.py
.. _RFC 6455: http://tools.ietf.org/html/rfc6455
.. _RFC 7692: http://tools.ietf.org/html/rfc7692
.. _Autobahn Testsuite: https://github.com/aaugustin/websockets/blob/master/compliance/README.rst
.. _PEP 3156: http://www.python.org/dev/peps/pep-3156/
.. _issue: https://github.com/aaugustin/websockets/issues/new
.. _pull request: https://github.com/aaugustin/websockets/compare/

.. toctree::
   :hidden:

   intro
   cheatsheet
   api
   deployment
   security
   design
   limitations
   changelog
   license
