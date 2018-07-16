import argparse
import asyncio
import readline
import sys
import threading

import websockets
from websockets.compatibility import asyncio_ensure_future


def print_during_input(string, redisplay_input=True):
    sys.stdout.write(
        '\r'                # Move to beginning of line
        '\u001B[2K'         # Erase entire current line (VT100)
        + string + '\n'     # Display string on its own line
    )
    if redisplay_input:
        sys.stdout.write('> ' + readline.get_line_buffer())
        sys.stdout.flush()


@asyncio.coroutine
def run_client(uri, loop, inputs, stop):
    websocket = yield from websockets.connect(uri)
    print_during_input("Connected to {}".format(uri))

    try:
        while True:
            incoming = asyncio_ensure_future(websocket.recv())
            outgoing = asyncio_ensure_future(inputs.get())
            done, pending = yield from asyncio.wait(
                [incoming, outgoing, stop],
                return_when=asyncio.FIRST_COMPLETED,
            )
            if incoming in done:
                print_during_input('< ' + incoming.result())
            else:
                incoming.cancel()

            if outgoing in done:
                yield from websocket.send(outgoing.result())
            else:
                outgoing.cancel()

            if stop in done:
                break

    finally:
        yield from websocket.close()
        print_during_input("Connection closed.", redisplay_input=False)

        loop.stop()


def main():
    # Parse command line arguments.
    parser = argparse.ArgumentParser(
        prog="python -m websockets",
        description="Interactive WebSocket client.",
        add_help=False,
    )
    parser.add_argument('uri', metavar='<uri>')
    args = parser.parse_args()

    # Create an event loop that will run in a background thread.
    loop = asyncio.new_event_loop()

    # Create a queue of user inputs. There's no need to limit its size.
    inputs = asyncio.Queue(loop=loop)

    # Create a stop condition when receiving SIGINT or SIGTERM.
    stop = asyncio.Future(loop=loop)

    # Schedule the task that will manage the connection.
    asyncio_ensure_future(run_client(args.uri, loop, inputs, stop), loop=loop)

    # Start the event loop in a background thread.
    thread = threading.Thread(target=loop.run_forever)
    thread.start()

    # Read from stdin in the main thread in order to receive signals.
    try:
        while True:
            # Since there's no size limit, put_nowait is identical to put.
            loop.call_soon_threadsafe(inputs.put_nowait, input('> '))
    except (KeyboardInterrupt, EOFError):   # ^C, ^D
        loop.call_soon_threadsafe(stop.set_result, None)

    # Wait for the event loop to terminate.
    thread.join()


if __name__ == '__main__':
    main()
