import sys

import atheris


with atheris.instrument_imports():
    from websockets.exceptions import SecurityError
    from websockets.http11 import Response
    from websockets.streams import StreamReader


def test_one_input(data):
    reader = StreamReader()
    reader.feed_data(data)
    reader.feed_eof()

    try:
        Response.parse(
            reader.read_line,
            reader.read_exact,
            reader.read_to_eof,
        )
    except (
        EOFError,  # connection is closed without a full HTTP response.
        SecurityError,  # response exceeds a security limit.
        LookupError,  # response isn't well formatted.
        ValueError,  # response isn't well formatted.
    ):
        pass


def main():
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
