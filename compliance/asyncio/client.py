import asyncio
import json
import logging

from websockets.asyncio.client import connect
from websockets.exceptions import WebSocketException


logging.basicConfig(level=logging.WARNING)

SERVER = "ws://localhost:9001"

AGENT = "websockets.asyncio"


async def get_case_count():
    async with connect(f"{SERVER}/getCaseCount") as ws:
        return json.loads(await ws.recv())


async def run_case(case):
    async with connect(
        f"{SERVER}/runCase?case={case}&agent={AGENT}",
        max_size=2**25,
    ) as ws:
        try:
            async for msg in ws:
                await ws.send(msg)
        except WebSocketException:
            pass


async def update_reports():
    async with connect(
        f"{SERVER}/updateReports?agent={AGENT}",
        open_timeout=60,
    ):
        pass


async def main():
    cases = await get_case_count()
    for case in range(1, cases + 1):
        print(f"Running test case {case:03d} / {cases}... ", end="\t")
        try:
            await run_case(case)
        except WebSocketException as exc:
            print(f"ERROR: {type(exc).__name__}: {exc}")
        except Exception as exc:
            print(f"FAIL: {type(exc).__name__}: {exc}")
        else:
            print("OK")
    print(f"Ran {cases} test cases")
    await update_reports()
    print("Updated reports")


if __name__ == "__main__":
    asyncio.run(main())
