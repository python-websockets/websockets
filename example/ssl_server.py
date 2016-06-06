#!/usr/bin/env python

import ssl, os
import asyncio
import websockets

async def counter(websocket, path):
    count = 0
    while True:
        await asyncio.sleep(0.5)
        count += 1
        await websocket.send(str(count))

class HTTPWebSocketServerProtocol(websockets.WebSocketServerProtocol):
    
    @asyncio.coroutine
    def handler(self):
        try:
            method, path, version = (yield from self.reader.readline())[:-2].decode().split()
            if method != 'GET' or not path.startswith('/') or version != 'HTTP/1.1':
                raise
            headers = {}
            while True:
                line = (yield from self.reader.readline())[:-2]
                if line == b'':
                    break
                key, content = line.decode('utf-8').split(': ', 1)
                headers[key] = content
            if 'Sec-WebSocket-Key' not in headers:
                self.writer.write('HTTP/1.0 200 OK\r\nContent-type: text/html\r\n\r\n'.encode())
                self.writer.write('''
                    <body>
                        <div>Count for <span id="val">0</span> time(s).<div>
                        <script>
                            var ws = new WebSocket("wss://"+window.location.host+"/");
                            ws.onmessage = function (event) {
                                document.getElementById("val").innerHTML = event.data;
                            };
                        </script>
                    <body>
                '''.encode())
                self.writer.close()
                return
            feed_buffer = ('%s %s %s\r\n' % (method, path, version)).encode()
            for key in headers:
                feed_buffer += ('%s: %s\r\n' % (key, headers[key])).encode()
            self.reader._buffer = bytearray(feed_buffer + b'\r\n') + self.reader._buffer
            yield from super().handler()
        finally:
            self.writer.close()
            self.ws_server.unregister(self)


if not os.path.exists('cert.pem'):
    os.system('openssl req -x509 -nodes -days 1000 -subj "/CN=websockets/" -newkey rsa:2048 -keyout cert.pem -out cert.pem')

context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
context.load_cert_chain(certfile='cert.pem')
context.set_ciphers('RSA')

start_server = websockets.serve(counter, 'localhost', 8443, klass=HTTPWebSocketServerProtocol, ssl=context)
print("Hi, please visit -> https://localhost:8443")

asyncio.get_event_loop().run_until_complete(start_server)
asyncio.get_event_loop().run_forever()
