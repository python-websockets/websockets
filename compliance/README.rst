Autobahn Testsuite
==================

General information and installation instructions are available at
https://github.com/crossbario/autobahn-testsuite.

Running the test suite
----------------------

All commands below must be run from the root directory of the repository.

To get acceptable performance, compile the C extension first:

.. code-block:: console

    $ python setup.py build_ext --inplace

Run each command in a different shell. Testing takes several minutes to complete
— wstest is the bottleneck. When clients finish, stop servers with Ctrl-C.

You can exclude slow tests by modifying the configuration files as follows::

    "exclude-cases": ["9.*", "12.*", "13.*"]

The test server and client applications shouldn't display any exceptions.

To test the servers:

.. code-block:: console

    $ PYTHONPATH=src python compliance/asyncio/server.py
    $ PYTHONPATH=src python compliance/sync/server.py

    $ docker run --interactive --tty --rm \
        --volume "${PWD}/compliance/config:/config" \
        --volume "${PWD}/compliance/reports:/reports" \
        --name fuzzingclient \
        crossbario/autobahn-testsuite \
        wstest --mode fuzzingclient --spec /config/fuzzingclient.json

    $ open compliance/reports/servers/index.html

To test the clients:

.. code-block:: console
    $ docker run --interactive --tty --rm \
        --volume "${PWD}/compliance/config:/config" \
        --volume "${PWD}/compliance/reports:/reports" \
        --publish 9001:9001 \
        --name fuzzingserver \
        crossbario/autobahn-testsuite \
        wstest --mode fuzzingserver --spec /config/fuzzingserver.json

    $ PYTHONPATH=src python compliance/asyncio/client.py
    $ PYTHONPATH=src python compliance/sync/client.py

    $ open compliance/reports/clients/index.html

Conformance notes
-----------------

Some test cases are more strict than the RFC. Given the implementation of the
library and the test client and server applications, websockets passes with a
"Non-Strict" result in these cases.

In 3.2, 3.3, 4.1.3, 4.1.4, 4.2.3, 4.2.4, and 5.15 websockets notices the
protocol error and closes the connection at the library level before the
application gets a chance to echo the previous frame.

In 6.4.1, 6.4.2, 6.4.3, and 6.4.4, even though it uses an incremental decoder,
websockets doesn't notice the invalid utf-8 fast enough to get a "Strict" pass.
These tests are more strict than the RFC.

Test case 7.1.5 fails because websockets treats closing the connection in the
middle of a fragmented message as a protocol error. As a consequence, it sends
a close frame with code 1002. The test suite expects a close frame with code
1000, echoing the close code that it sent. This isn't required. RFC 6455 states
that "the endpoint typically echos the status code it received", which leaves
the possibility to send a close frame with a different status code.
