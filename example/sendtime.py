#!/usr/bin/env python

import asyncio
import datetime
import random
import websockets

async def time(websocket, path):
    while True:
        now = datetime.datetime.utcnow().isoformat() + 'Z'
        await websocket.send(now)
        await asyncio.sleep(random.random() * 3)

class HTTPWebSocketServerProtocol(websockets.WebSocketServerProtocol):
	
	def hook_for_http_response(self, path, headers):
		try:
			with open('showtime.html', 'rb') as fp:
				response = 'HTTP/1.0 200 OK\r\nContent-type: text/html\r\n\r\n'
				self.writer.write(response.encode())
				while True:
					data = fp.read(4096)
					if not data:
						break
					self.writer.write(data)
		except Exception as e:
			print(e)
			self.writer.write('HTTP/1.0 404 Not Found\r\n\r\nFile not found'.encode())
		finally:
			self.writer.close()

start_server = websockets.serve(time, '127.0.0.1', 5678, klass=HTTPWebSocketServerProtocol)
print("Hi, please visit -> http://127.0.0.1:5678")

asyncio.get_event_loop().run_until_complete(start_server)
asyncio.get_event_loop().run_forever()
