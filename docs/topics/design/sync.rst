.. currentmodule:: websockets

How many threads do we need?
----------------------------

1. One user thread
..................

We need at least one thread to execute the user's logic. For clients, this is
the thread that opens the connection. For servers, due to inversion of control,
this is the thread creatad by the server to handle the connection. Either way,
the user gets a :class:`~sync.protocol.Protocol` instance.

2. One library thread
.....................

Even if the user doesn't interact with the connection e.g. they don't receive
messages and they send messages infrequently, we still want to respond to pings.
Since we use blocking I/O, this requires a thread for reading from the network.

This thread runs ``recv_events()``. It exits if and only the socket is closed.
In other words, it must exit once the socket is closed for reading or writing
and it must close the socket for reading and writing before exiting.

3. No closing thread
....................

When the closing handshake is started, we want to enforce a close timeout, which
means closing the socket after 10 seconds by default if it isn't already closed.

There are two ways to achieve this:

1. When the closing hanshake is started, start a closing thread that waits for
   ``recv_events()`` to exit with a 10 seconds timeout. If the timeout elapses,
   the closing thread closes the socket. A separate thread is necessary because
   ``recv_events()`` can start the closing handshake but cannot wait for itself.
2. When the closing handshake is started from the user thread, in that thread,
   wait for ``recv_events()`` to exit with a 10 second timeout. When the closing
   handshake is started from the library thread, set a timeout on reading from
   the socket and close the socket if a read returns no data.

We choose option 2 because:

* Implementing two timeout mechanisms sounds less error-prone than coordinating
  three threads.
* Once the closing handshake is started, we want calls from the user thread to
  wait for the connection to be closed and return the correct exception so we
  need to handle the two cases differently anyway.

How do we handle concurrency?
-----------------------------

The user may run threads sharing access to the :class:`~sync.protocol.Protocol`
instance. We want websockets to be concurrency-safe.

For reading, attempting concurrent operations should raise :exc:`RuntimeError`.
Since reads can be slow, serialization could lead to misleading behavior e.g. it
isn't obvious whether a read is waiting for data or waiting for another read to
complete. This could hide deadlocks.

Also, concurrent reads are likely to be programming mistakes because they can
lead to non-deterministic behavior. Which read gets the next message? Multiple
consumers for incoming messages can be implemented by adding a queue.

For writing, attempting concurrent operations should result in serialization.
Since writes should be fast, serialization shouldn't to create issues. If it
leads to a deadlock, users will notice.

How many locks do we need?
--------------------------

1. Connection lock
..................

Both the user thread and the library thread may interact with the Sans-I/O
:class:`~connection.Connection` wrapped by the :class:`~sync.protocol.Protocol`.
This requires a mutex for serialization, ``conn_mutex``.

Critical sections protected with ``conn_mutex`` must include writing data to the
socket to guarantee that outgoing data is sent in the expected order.

Writing pings in the user thread and reading pongs in the library thread both
modify ``pings``. We reuse ``conn_mutex`` to protect access without creating a
risk of deadlocks.

2. No read lock
...............

The library thread reads incoming data from the socket, feeds it to the
:class:`~connection.Connection`, and pushes events to ``recv_messages``.

These actions happen sequentially in a single thread. Feeding data to the
:class:`~connection.Connection` is protected by the connection lock.
``recv_messages`` is thread-safe.

:meth:`~sync.protocol.Protocol.__iter__`, :meth:`~sync.protocol.Protocol.recv`,
and :meth:`~sync.protocol.Protocol.recv_streaming` are serialized by
``recv_messages.mutex``, which acts as the read lock.

(Calling :meth:`~sync.protocol.Protocol.recv` while
:meth:`~sync.protocol.Protocol.__iter__` is running isn't guaranteed to raise
:exc:`RuntimeError``. However, it will do so often enough for users to notice.)

3. No write lock
................

`:meth:`~sync.protocol.Protocol.send`, `:meth:`~sync.protocol.Protocol.close`,
`:meth:`~sync.protocol.Protocol.ping`, and `:meth:`~sync.protocol.Protocol.pong`
are sufficiently protected by ``conn_mutex``.

It is possible to hit a :exc:`RuntimeError`

can. This requires a mutex for serialization, ``send_mutex``.

Specifically, the write lock must ensure that data is sent to the network in the
same order

We cannot reuse ``conn_mutex`` becase ``close()`` must release it to let the
closing handshake complete, but it should still hold the write lock.

It might be possible to use the same lock for reads and writes, however that
wouldn't bring significant benefits.

How do we prevent deadlocks?
----------------------------

It is allowed to take locks in the following order:

* ``conn_mutex``
* ``messages.mutex``
* ``send_mutex``
    * ``conn_mutex``
    * ``pings_mutex``
* ``ping_mutex``

This prevents cycles and therefore deadlocks.

``recv_messages`` enforces synchronization between the library thread and the
user thread reading messages with a pair of events that make it behave like a
queue with a maximum size of one message. Serialization ensures that no more
than one thread can wait on these events, which makes deadlocks impossible.






Handling connection termination
-------------------------------




How do we handle connection errors?
-----------------------------------

In ``sock.recv()``
..................

``sock.recv()`` may raise ``OSError``. (See socketmodule.c.) All errors codes
listed in ``man 2 recv`` that may happen in the context of an established TCP
connection and that aren't handled automatically by Python (EINTR) signal that
the connection is closed or unresponsive:

* EAGAIN, EWOULDBLOCK (Linux): the connection is unresponsive; this happens only
  when a timeout is set on the socket i.e. during the closing handshake.
* EBADF, ECONNREFUSED (Linux), ECONNRESET (BSD): the connection is closed.

From the perspective of the WebSocket connection, this means that no more data
will be received, perhaps because we aren't going to wait for it. It doesn't
matter whether the TCP connection was closed properly. We signal this to the
Sans-I/O layer with ``receive_eof()``.

The ``OSError`` is captured in ``recv_events_exc`` and chained to
``ConnectionClosedError`` in ``recv()``, ``recv_streaming()``, and
``ensure_open()``.

In ``sock.sendall()`` and ``sock.shutwdown()``
..............................................

Similarly, ``sock.sendall()`` and ``sock.shutwdown()`` may raise ``OSError``,
meaning that the connection is unresponsive or closed.

From the perspective of the WebSocket connection, this means that no more data
can be sent. While reading could still be possible in theory...












                    # The TCP connection should be closed first by the server.
                    See 7.1.7 # of RFC 6455. Therefore, the following sequence
                    is expected.

                    # 1. The server starts the TCP closing handshake with a FIN
                    packet. #    This happens when data_to_send() signals EOF
                    with an empty #    bytestring, triggering
                    sock.shutdown(SHUT_WR).

                    # 2. The client reads until EOF and completes the TCP
                    closing #    handshake with a FIN packet. Again, this
                    happens when #    data_to_send() signals EOF with an empty
                    bytestring, triggering #    sock.shutdown(SHUT_WR). Then,
                    recv_events() terminates and #    calls sock.close().

                    # 3. The server reads until reaching EOF. recv_events()
                    terminates #    and calls sock.close(). This doesn't send a
                    packet.




                    except OSError as exc:  # sendall() or shutdown() failed
                        original_exc = exc self.logger.debug("error while
                        sending data", exc_info=True)
                    except Exception as exc:
                        original_exc = exc self.logger.error("unexpected error
                        while sending data", exc_info=True)
