Autobahn Testsuite
==================

General information and installation instructions are available at
http://autobahn.ws/testsuite.

Running the test suite
----------------------

To test the server::

    $ python test_server.py
    $ wstest -m fuzzingclient

To test the client::

    $ wstest -m fuzzingserver
    $ python test_client.py

Run the first command in a shell. Run the second command in another shell. It
should take about one minute to complete. Then kill the first one with Ctrl-C.

The test client or server shouldn't display any exceptions. The results are
stored in reports/index.html.

Note that the Autobahn software only supports Python 2, while websockets only
supports Python 3; you need two different environments.

Conformance notes
-----------------

Test cases 6.4.2, 6.4.3, and 6.4.4 are actually more strict than the RFC.
Given its implementation, ``websockets`` gets a "Non-Strict".
