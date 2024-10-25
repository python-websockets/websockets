import json
import logging

from websockets.exceptions import WebSocketException
from websockets.sync.client import connect


logging.basicConfig(level=logging.WARNING)

SERVER = "ws://localhost:9001"

AGENT = "websockets.sync"


def get_case_count():
    with connect(f"{SERVER}/getCaseCount") as ws:
        return json.loads(ws.recv())


def run_case(case):
    with connect(
        f"{SERVER}/runCase?case={case}&agent={AGENT}",
        max_size=2**25,
    ) as ws:
        try:
            for msg in ws:
                ws.send(msg)
        except WebSocketException:
            pass


def update_reports():
    with connect(
        f"{SERVER}/updateReports?agent={AGENT}",
        open_timeout=60,
    ):
        pass


def main():
    cases = get_case_count()
    for case in range(1, cases + 1):
        print(f"Running test case {case:03d} / {cases}... ", end="\t")
        try:
            run_case(case)
        except WebSocketException as exc:
            print(f"ERROR: {type(exc).__name__}: {exc}")
        except Exception as exc:
            print(f"FAIL: {type(exc).__name__}: {exc}")
        else:
            print("OK")
    print(f"Ran {cases} test cases")
    update_reports()
    print("Updated reports")


if __name__ == "__main__":
    main()
