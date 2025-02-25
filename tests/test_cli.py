import io
import os
import re
import unittest
from unittest.mock import patch

from websockets.cli import *
from websockets.exceptions import ConnectionClosed
from websockets.version import version

# Run a test server in a thread. This is easier than running an asyncio server
# because we would have to run main() in a thread, due to using asyncio.run().
from .sync.server import get_uri, run_server


vt100_commands = re.compile(r"\x1b\[[A-Z]|\x1b[78]|\r")


def remove_commands_and_prompts(output):
    return vt100_commands.sub("", output).replace("> ", "")


def add_connection_messages(output, server_uri):
    return f"Connected to {server_uri}.\n{output}Connection closed: 1000 (OK).\n"


class CLITests(unittest.TestCase):
    def run_main(self, argv, inputs="", close_input=False, expected_exit_code=None):
        # Replace sys.stdin with a file-like object backed by a file descriptor
        # for compatibility with loop.connect_read_pipe().
        stdin_read_fd, stdin_write_fd = os.pipe()
        stdin = io.FileIO(stdin_read_fd)
        self.addCleanup(stdin.close)
        os.write(stdin_write_fd, inputs.encode())
        if close_input:
            os.close(stdin_write_fd)
        else:
            self.addCleanup(os.close, stdin_write_fd)
        # Replace sys.stdout with a file-like object to record outputs.
        stdout = io.StringIO()
        with patch("sys.stdin", new=stdin), patch("sys.stdout", new=stdout):
            # Catch sys.exit() calls when expected.
            if expected_exit_code is not None:
                with self.assertRaises(SystemExit) as raised:
                    main(argv)
                self.assertEqual(raised.exception.code, expected_exit_code)
            else:
                main(argv)
            return stdout.getvalue()

    def test_version(self):
        output = self.run_main(["--version"])
        self.assertEqual(output, f"websockets {version}\n")

    def test_receive_text_message(self):
        def text_handler(websocket):
            websocket.send("café")

        with run_server(text_handler) as server:
            server_uri = get_uri(server)
            output = self.run_main([server_uri], "")
        self.assertEqual(
            remove_commands_and_prompts(output),
            add_connection_messages("\n< café\n", server_uri),
        )

    def test_receive_binary_message(self):
        def binary_handler(websocket):
            websocket.send(b"tea")

        with run_server(binary_handler) as server:
            server_uri = get_uri(server)
            output = self.run_main([server_uri], "")
        self.assertEqual(
            remove_commands_and_prompts(output),
            add_connection_messages("\n< (binary) 746561\n", server_uri),
        )

    def test_send_message(self):
        def echo_handler(websocket):
            websocket.send(websocket.recv())

        with run_server(echo_handler) as server:
            server_uri = get_uri(server)
            output = self.run_main([server_uri], "hello\n")
        self.assertEqual(
            remove_commands_and_prompts(output),
            add_connection_messages("\n< hello\n", server_uri),
        )

    def test_close_connection(self):
        def wait_handler(websocket):
            with self.assertRaises(ConnectionClosed):
                websocket.recv()

        with run_server(wait_handler) as server:
            server_uri = get_uri(server)
            output = self.run_main([server_uri], "", close_input=True)
        self.assertEqual(
            remove_commands_and_prompts(output),
            add_connection_messages("", server_uri),
        )

    def test_connection_failure(self):
        output = self.run_main(["ws://localhost:54321"], expected_exit_code=1)
        self.assertTrue(
            output.startswith("Failed to connect to ws://localhost:54321: ")
        )

    def test_no_args(self):
        output = self.run_main([], expected_exit_code=2)
        self.assertEqual(output, "usage: websockets [--version | <uri>]\n")
