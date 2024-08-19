Memory and buffers
==================

.. currentmodule:: websockets

In most cases, memory usage of a WebSocket server is proportional to the
number of open connections. When a server handles thousands of connections,
memory usage can become a bottleneck.

Memory usage of a single connection is the sum of:

1. the baseline amount of memory that websockets uses for each connection;
2. the amount of memory needed by your application code;
3. the amount of data held in buffers.

Connection
----------

Compression settings are the primary factor affecting how much memory each
connection uses.

The :mod:`asyncio` implementation with default settings uses 64 KiB of memory
for each connection.

You can reduce memory usage to 14 KiB per connection if you disable compression
entirely.

Refer to the :doc:`topic guide on compression <../topics/compression>` to
learn more about tuning compression settings.

Application
-----------

Your application will allocate memory for its data structures. Memory usage
depends on your use case and your implementation.

Make sure that you don't keep references to data that you don't need anymore
because this prevents garbage collection.

Buffers
-------

Typical WebSocket applications exchange small messages at a rate that doesn't
saturate the CPU or the network. Buffers are almost always empty. This is the
optimal situation. Buffers absorb bursts of incoming or outgoing messages
without having to pause reading or writing.

If the application receives messages faster than it can process them, receive
buffers will fill up when. If the application sends messages faster than the
network can transmit them, send buffers will fill up.

When buffers are almost always full, not only does the additional memory usage
fail to bring any benefit, but latency degrades as well. This problem is called
bufferbloat_. If it cannot be resolved by adding capacity, typically because the
system is bottlenecked by its output and constantly regulated by
:ref:`backpressure <backpressure>`, then buffers should be kept small to ensure
that backpressure kicks in quickly.

.. _bufferbloat: https://en.wikipedia.org/wiki/Bufferbloat

To sum up, buffers should be sized to absorb bursts of messages. Making them
larger than necessary often causes more harm than good.

There are three levels of buffering in an application built with websockets.

TCP buffers
...........

The operating system allocates buffers for each TCP connection. The receive
buffer stores data received from the network until the application reads it.
The send buffer stores data written by the application until it's sent to
the network and acknowledged by the recipient.

Modern operating systems adjust the size of TCP buffers automatically to match
network conditions. Overall, you shouldn't worry about TCP buffers. Just be
aware that they exist.

In very high throughput scenarios, TCP buffers may grow to several megabytes
to store the data in flight. Then, they can make up the bulk of the memory
usage of a connection.

I/O library buffers
...................

I/O libraries like :mod:`asyncio` may provide read and write buffers to reduce
the frequency of system calls or the need to pause reading or writing.

You should keep these buffers small. Increasing them can help with spiky
workloads but it can also backfire because it delays backpressure.

* In the new :mod:`asyncio` implementation, there is no library-level read
  buffer.

  There is a write buffer. The ``write_limit`` argument of
  :func:`~asyncio.client.connect` and :func:`~asyncio.server.serve` controls its
  size. When the write buffer grows above the high-water mark,
  :meth:`~asyncio.connection.Connection.send` waits until it drains under the
  low-water mark to return. This creates backpressure on coroutines that send
  messages.

* In the legacy :mod:`asyncio` implementation, there is a library-level read
  buffer. The ``read_limit`` argument of :func:`~legacy.client.connect` and
  :func:`~legacy.server.serve` controls its size. When the read buffer grows
  above the high-water mark, the connection stops reading from the network until
  it drains under the low-water mark. This creates backpressure on the TCP
  connection.

  There is a write buffer. It as controlled by ``write_limit``. It behaves like
  the new :mod:`asyncio` implementation described above.

* In the :mod:`threading` implementation, there are no library-level buffers.
  All I/O operations are performed directly on the :class:`~socket.socket`.

websockets' buffers
...................

Incoming messages are queued in a buffer after they have been received from the
network and parsed. A larger buffer may help a slow applications handle bursts
of messages while remaining responsive to control frames.

The memory footprint of this buffer is bounded by the product of ``max_size``,
which controls the size of items in the queue, and ``max_queue``, which controls
the number of items.

The ``max_size`` argument of :func:`~asyncio.client.connect` and
:func:`~asyncio.server.serve` defaults to 1 MiB. Most applications never receive
such large messages. Configuring a smaller value puts a tighter boundary on
memory usage. This can make your application more resilient to denial of service
attacks.

The behavior of the ``max_queue`` argument of :func:`~asyncio.client.connect`
and :func:`~asyncio.server.serve` varies across implementations.

* In the new :mod:`asyncio` implementation, ``max_queue`` is the high-water mark
  of a queue of incoming frames. It defaults to 16 frames. If the queue grows
  larger, the connection stops reading from the network until the application
  consumes messages and the queue goes below the low-water mark. This creates
  backpressure on the TCP connection.

  Each item in the queue is a frame. A frame can be a message or a message
  fragment. Either way, it must be smaller than ``max_size``, the maximum size
  of a message. The queue may use up to ``max_size * max_queue`` bytes of
  memory. By default, this is 16 MiB.

* In the legacy :mod:`asyncio` implementation, ``max_queue`` is the maximum
  size of a queue of incoming messages. It defaults to 32 messages. If the queue
  fills up, the connection stops reading from the library-level read buffer
  described above. If that buffer fills up as well, it will create backpressure
  on the TCP connection.

  Text messages are decoded before they're added to the queue. Since Python can
  use up to 4 bytes of memory per character, the queue may use up to ``4 *
  max_size * max_queue`` bytes of memory. By default, this is 128 MiB.

* In the :mod:`threading` implementation, there is no queue of incoming
  messages. The ``max_queue`` argument doesn't exist. The connection keeps at
  most one message in memory at a time.
