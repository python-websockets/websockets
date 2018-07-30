import argparse
import asyncio
import os
import signal
import sys
import threading

import websockets
from websockets.compatibility import asyncio_ensure_future
from websockets.exceptions import format_close


def exit_from_event_loop_thread(loop, stop):
    loop.stop()
    if not stop.done():
        # When exiting the thread that runs the event loop, raise
        # KeyboardInterrupt in the main thead to exit the program.
        try:
            ctrl_c = signal.CTRL_C_EVENT    # Windows
        except AttributeError:
            ctrl_c = signal.SIGINT          # POSIX
        os.kill(os.getpid(), ctrl_c)


def print_during_input(string):
    sys.stdout.write(
        '\N{ESC}7'                  # Save cursor position
        '\N{LINE FEED}'             # Add a new line
        '\N{ESC}[A'                 # Move cursor up
        '\N{ESC}[L'                 # Insert blank line, scroll last line down
        '{string}\N{LINE FEED}'     # Print string in the inserted blank line
        '\N{ESC}8'                  # Restore cursor position
        '\N{ESC}[B'                 # Move cursor down
        .format(string=string)
    )
    sys.stdout.flush()


def print_over_input(string):
    sys.stdout.write(
        '\N{CARRIAGE RETURN}'       # Move cursor to beginning of line
        '\N{ESC}[K'                 # Delete current line
        '{string}\N{LINE FEED}'
        .format(string=string)
    )
    sys.stdout.flush()


@asyncio.coroutine
def run_client(uri, loop, inputs, stop):
    try:
        websocket = yield from websockets.connect(uri)
    except Exception as exc:
        print_over_input("Failed to connect to {}: {}.".format(uri, exc))
        exit_from_event_loop_thread(loop, stop)
        return
    else:
        print_during_input("Connected to {}.".format(uri))

    try:
        while True:
            incoming = asyncio_ensure_future(websocket.recv())
            outgoing = asyncio_ensure_future(inputs.get())
            done, pending = yield from asyncio.wait(
                [incoming, outgoing, stop],
                return_when=asyncio.FIRST_COMPLETED,
            )

            # Cancel pending tasks to avoid leaking them.
            if incoming in pending:
                incoming.cancel()
            if outgoing in pending:
                outgoing.cancel()

            if incoming in done:
                try:
                    message = incoming.result()
                except websockets.ConnectionClosed:
                    break
                else:
                    print_during_input('< ' + message)

            if outgoing in done:
                message = outgoing.result()
                yield from websocket.send(message)

            if stop in done:
                break

    finally:
        yield from websocket.close()
        close_status = format_close(
            websocket.close_code, websocket.close_reason)

        print_over_input(
            "Connection closed: {close_status}."
            .format(close_status=close_status)
        )

        exit_from_event_loop_thread(loop, stop)


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
            message = input('> ')
            loop.call_soon_threadsafe(inputs.put_nowait, message)
    except (KeyboardInterrupt, EOFError):   # ^C, ^D
        loop.call_soon_threadsafe(stop.set_result, None)

    # Wait for the event loop to terminate.
    thread.join()


if __name__ == '__main__':
    main()
