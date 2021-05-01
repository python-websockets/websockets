import asyncio
import websockets


async def recv(ws):
    while True:
        print(await ws.recv())


async def send(ws, q):
    while True:
        await ws.send(await q.get())


async def client(user_input_queue):
    async with websockets.connect('ws://127.0.0.1:50001') as ws:
        print('start client')

        recv_task = asyncio.create_task(recv(ws))
        send_task = asyncio.create_task(send(ws, user_input_queue))

        await asyncio.gather(recv_task, send_task)


async def inputter():
    return await asyncio.get_event_loop().run_in_executor(None, lambda: input('> '))


async def main():
    user_input_queue = asyncio.Queue()

    client_task = asyncio.create_task(client(user_input_queue))

    while True:
        user_input = await inputter()
        print(user_input)
        await user_input_queue.put(user_input)

    await recv_task


asyncio.run(main())
