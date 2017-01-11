#!/usr/bin/env python

import asyncio
import json
import random
import websockets

def create_random_id():
    max_uint32 = 2**32 - 1
    return random.randint(0, max_uint32)

# This example shows how to multiplex requests from a server
# using asyncio Future.

class Client:

    def __init__(self, websockets_path):
        self._websocket_connect = websockets.connect(websockets_path)
        self._websocket = None

        self._requests = {}

    # Define enter method for the beginning of a with statement.
    async def __aenter__(self):
        self._websocket = await self._websocket_connect.__aenter__()
        # This is the task listening for incoming responses from the server.
        loop = asyncio.get_event_loop()
        self._task = loop.create_task(self._receive_loop())
        return self

    # Define exit method for the end of a with statement.
    async def __aexit__(self, *args):
        # Stop the receive loop before stopping the websocket connection
        # otherwise an exception will be thrown in the receive loop.
        self._task.cancel()
        await self._websocket_connect.__aexit__(*args)

    async def _receive_loop(self):
        while True:
            # Listen for new responses from the server.
            response = await self._websocket.recv()
            response = json.loads(response)
            assert "id" in response
            ident = response["id"]

            # Lookup the future in the requests dict.
            future = self._requests[ident]
            del self._requests[ident]

            # Set the result for the future.
            future.set_result(response)

    # Make a query to the server.
    async def query(self, command, *params):
        ident = create_random_id()
        request = {
            "command": command,
            "id": ident,
            "params": params
        }
        print("Sending:", json.dumps(request, indent=2))
        request = json.dumps(request)

        # Send our request to the server.
        await self._websocket.send(request)

        future = asyncio.Future()
        self._requests[ident] = future

        # Await our response from the server.
        response = await future

        print("Received:", json.dumps(response, indent=2))

        assert "error" in response
        assert "result" in response

        # Return the result.
        return response["error"], response["result"]

async def hello():
    async with Client('ws://localhost:8765') as client:
        error, result = await client.query("myapp_do_something",
                                           12, "foo")
        print(error, result)

asyncio.get_event_loop().run_until_complete(hello())

