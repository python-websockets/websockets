import asyncio
import logging
import json
from websockets.asyncio.client import connect

# import debugpy

# # Allow VS Code to attach
# debugpy.listen(("0.0.0.0", 5678))  # Use the port you've specified
# print("Waiting for debugger to attach...")
# debugpy.wait_for_client()

logging.getLogger(__name__)
logging.basicConfig(
    format="%(asctime)s %(module)s:%(lineno)d %(levelname)8s | %(message)s",
    datefmt="%Y/%m/%d %H:%M:%S",
    level=logging.DEBUG,
)

class MyClient:

    def __init__(self):
        self.keep_alive = True

    async def run(self):

        async with connect(
            f"wss://ws.kraken.com/v2",
            ping_interval=30,
            # max_queue=None,  # having this enabled doesn't cause problems
        ) as socket:
            await socket.send(
                json.dumps(
                    {
                        "method": "subscribe",
                        "params": {
                            "channel": "book",
                            "symbol": [
                                "BTC/USD",
                                "DOT/USD",
                                "ETH/USD",
                                "MATIC/USD",
                                "BTC/EUR",
                                "DOT/EUR",
                                "ETH/EUR",
                                "XLM/USD",
                                "XLM/EUR",
                            ],
                            "depth": 100
                        },
                    }
                )
            )

            while self.keep_alive:
                try:
                    _message = await asyncio.wait_for(socket.recv(), timeout=10)
                except TimeoutError:
                    pass
                except asyncio.CancelledError:
                    self.keep_alive = False
                else:
                    try:
                        message = json.loads(_message)
                    except ValueError:
                        pass

    async def __aenter__(self):
        self.task: asyncio.Task = asyncio.create_task(self.run())
        return self

    async def __aexit__(self, *args, **kwargs):
        self.keep_alive = False
        if hasattr(self, "task") and not self.task.done():
            await self.task


async def main():
    async with MyClient():
        await asyncio.sleep(3)


if __name__ == "__main__":
    asyncio.run(main())
