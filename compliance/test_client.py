import json
import logging
import urllib.parse

import asyncio
import websockets


logging.basicConfig(level=logging.WARNING)

# Uncomment this line to make only websockets more verbose.
# logging.getLogger('websockets').setLevel(logging.DEBUG)


SERVER = 'ws://127.0.0.1:8642'
AGENT = 'websockets'


async def get_case_count(server):
    uri = server + '/getCaseCount'
    ws = await websockets.connect(uri)
    msg = await ws.recv()
    await ws.close()
    return json.loads(msg)


async def run_case(server, case, agent):
    uri = server + '/runCase?case={}&agent={}'.format(case, agent)
    ws = await websockets.connect(uri, max_size=2 ** 25, max_queue=1)
    while True:
        try:
            msg = await ws.recv()
            await ws.send(msg)
        except websockets.ConnectionClosed:
            break


async def update_reports(server, agent):
    uri = server + '/updateReports?agent={}'.format(agent)
    ws = await websockets.connect(uri)
    await ws.close()


async def run_tests(server, agent):
    cases = await get_case_count(server)
    for case in range(1, cases + 1):
        print("Running test case {} out of {}".format(case, cases), end="\r")
        await run_case(server, case, agent)
    print("Ran {} test cases               ".format(cases))
    await update_reports(server, agent)


main = run_tests(SERVER, urllib.parse.quote(AGENT))
asyncio.get_event_loop().run_until_complete(main)
