import sys

import atheris


with atheris.instrument_imports():
    from websockets.exceptions import SecurityError
    from websockets.http11 import Request
    from websockets.streams import StreamReader


def test_one_input(data):
    reader = StreamReader()
    reader.feed_data(data)
    reader.feed_eof()

    try:
        Request.parse(
            reader.read_line,
        )
    except (
        EOFError,  # connection is closed without a full HTTP request
        SecurityError,  # request exceeds a security limit
        ValueError,  # request isn't well formatted
    ):
        pass


def main():
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
