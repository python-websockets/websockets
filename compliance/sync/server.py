import logging

from websockets.exceptions import WebSocketException
from websockets.sync.server import serve


logging.basicConfig(level=logging.WARNING)

HOST, PORT = "0.0.0.0", 9003


def echo(ws):
    try:
        for msg in ws:
            ws.send(msg)
    except WebSocketException:
        pass


def main():
    with serve(
        echo,
        HOST,
        PORT,
        server_header="websockets.asyncio",
        max_size=2**25,
    ) as server:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
