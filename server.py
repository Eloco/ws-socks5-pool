#!/usr/bin/env python
# coding=utf-8

import asyncio
import websockets
import json
import socks
import base64
from aiohttp import web
import traceback
import random
import uuid
import pickle
from collections import defaultdict

# ===============================
# Global Storage for Proxies
# ===============================
events = defaultdict(asyncio.Event)
proxies = []  # {"region1": [[websocket1, ip1], [websocket2, ip2]], ...}
receive_queues = {}
lock = asyncio.Lock()  # Ensure thread-safe access to proxies
recv_lock = asyncio.Lock()  # Prevent concurrent recv calls on WebSocket
BufferSize = 4096

# ===============================
# WebSocket Server (Handle Proxy Connections)
# ===============================
async def register_proxy(websocket):
    queue = asyncio.Queue()
    try:
        # Ensure that only one coroutine can receive from the WebSocket at a time
        count=0
        async for message in websocket:
            if count==0:
                count=count+1
                data = json.loads(message)
                region = data.get("region", "unknown")
                country = data.get("country", "unknown")
                ip = data.get("ip", "unknown")
                sid = data.get("sid", "unknown")
                receive_queues[sid] = queue

                # Add the proxy to the region
                async with lock:
                    proxies.append({"region": region,
                                     "websocket": websocket,
                                     "country": country,
                                     "ip": ip,
                                     "sid": sid,
                                     })
                    print(f"Proxy {ip} registered in region: {region}, sid: {sid}")


            else:
                sid = list(filter(lambda proxy: proxy["websocket"] == websocket, proxies))[0]["sid"]
                if message:
                    await queue.put(message)
                    if sid not in events:
                        events[sid] = asyncio.Event() 
                if sid in events:
                    events[sid].set()


    except Exception as e:
        traceback.print_exc()
        print(f"Error handling WebSocket connection: {e}")
    finally:
        async with lock:
            remove_proxy = list(filter(lambda proxy: proxy["websocket"] == websocket, proxies))[0]
            sid = remove_proxy["sid"]
            proxies.remove(remove_proxy)
        # Close the WebSocket connection
        await websocket.close()
        del queue
        if sid in events:
            events[sid].set()
            del events[sid]

        print(f"ws closed for {remove_proxy['ip']} in region: {remove_proxy['region']}")

async def websocket_server():
    """Start the WebSocket server to accept proxy connections."""
    print("WebSocket Server Started on ws://localhost:8765")
    server = await websockets.serve(register_proxy, "0.0.0.0", 8765)
    await server.wait_closed()  # 等待服务器关闭

async def send_large_message(client_writer, message, chunk_size=1024):
    # 将消息按指定的 chunk_size 切分
    for i in range(0, len(message), chunk_size):
        chunk = message[i:i+chunk_size]
        client_writer.write(chunk)
        await client_writer.drain()

    print("success send chunk")
    await client_writer.drain()

# ===============================
# SOCKS5 Proxy Server
# ===============================
def encrypt_binary_to_string(binary_data):
    return base64.b64encode(binary_data).decode('utf-8')

def decrypt_string_to_binary(encoded_string):
    return base64.b64decode(encoded_string)

async def handle_socks5_connection(client_reader, client_writer,client_id):
    """Handle a single SOCKS5 connection asynchronously."""
    ws_send_data={"client_id": client_id}
    try:
        proxy = await find_proxy_for_request()
        if proxy:
            proxy_ws=proxy["websocket"]
            sid=proxy["sid"]
        else:
            print("No available proxy.")
            return

        count=0
        while True:
            print("<count>",count)
            count+=1
            print("Waiting for data from client...")
            if client_reader.at_eof():
                ws_send_data["data"] = b"eof"
                binary_data = pickle.dumps(ws_send_data)
                await proxy_ws.send(binary_data)
                print("Connection closed by client<2>")
                client_writer.close()
                return
            try:
                print("ready client_data")
                client_data = await asyncio.wait_for(client_reader.read(BufferSize), timeout=5.0)  # 超时为5秒
                # client_data = await read_all_data(client_reader)
                print("read client_data",client_data[:10])
            except Exception as e:
                print(f"Error: timeout will close")
                client_writer.close()
                return

            if not client_data:
                print("Connection closed by client<3>")
                ws_send_data["data"] = b"eof"
                binary_data = pickle.dumps(ws_send_data)
                await proxy_ws.send(binary_data)
                client_writer.close()
                return


            if proxy:
                ws_send_data["data"] = client_data
                print("send_remote_ws_message",ws_send_data["data"][:10])
                binary_data = pickle.dumps(ws_send_data)
                await proxy_ws.send(binary_data)

                print(f"Continuing execution after waiting for {sid}.")
                try:
                    await asyncio.wait_for(events[sid].wait(), timeout=10)
                except:
                    print(f"events wait timeout 10s")
                    client_writer.close()
                    return
                events[sid].clear()  # 等待对应 sid 的事件被触发

                queue = receive_queues.get(sid)
                message = await queue.get()
                message = decrypt_string_to_binary(message)
                print("recv_remote_ws_message",message)

                if message==b"eof":
                    print("Connection closed by client<4>")
                    ws_send_data["data"] = b"eof"
                    binary_data = pickle.dumps(ws_send_data)
                    await proxy_ws.send(binary_data)
                    client_writer.close()
                    return

                await send_large_message(client_writer, message)
                print("send_client_msg",message[:10])
            else:
                print("No available proxy.")
                break

    except Exception as e:
        traceback.print_exc()
        print(f"Error handling SOCKS5 connection: {e}")
    finally:
        try:
            ws_send_data["data"] = b"eof"
            binary_data = pickle.dumps(ws_send_data)
            await proxy_ws.send(binary_data)
            client_writer.close()
        except:pass
        client_writer.close()

async def handle_client(client_socket,client_id):
    client_reader, client_writer = await asyncio.open_connection(sock=client_socket)
    await handle_socks5_connection(client_reader, client_writer, client_id)

async def start_socks5_proxy_server():
    """Start the SOCKS5 Proxy server with async handling."""
    server_socket = socks.socksocket()
    server_socket.bind(('0.0.0.0', 1080))  # Bind to port 1080
    server_socket.listen(100)
    server_socket.setblocking(False)  # Set non-blocking

    print("SOCKS5 Proxy Server started on port 1080")

    loop = asyncio.get_event_loop()
    while True:
        client_socket, client_address = await loop.sock_accept(server_socket)
        print(f"Client connected from {client_address}")
        client_id = str(uuid.uuid4())
        # 异步处理每一个客户端连接
        asyncio.create_task(handle_client(client_socket,client_id))

async def find_proxy_for_request():
    """Find an available proxy WebSocket to forward the request."""
    async with lock:
        if proxies:
            proxy = random.choice(proxies)
            return proxy
    return None

# ===============================
# HTTP Proxy Server (Handle Client Requests)
# ===============================
async def get_all_proxies(request):
    """Retrieve all proxy info (IP and region) from the proxies pool."""
    all_proxies = []
    async with lock:  # Use the async lock to ensure thread safety
        for proxy in proxies:
            all_proxies.append({"country": proxy["country"],
                                "region": proxy["region"],
                                "ip": proxy["ip"],
                                "sid": proxy["sid"]})
    return web.Response(text=json.dumps(all_proxies, indent=2), content_type='application/json')

async def start_http_proxy_server():
    """Start the HTTP Proxy server asynchronously using aiohttp."""
    app = web.Application()
    app.router.add_get('/allproxy', get_all_proxies)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    print("HTTP Proxy Server Started on port 8080")

# ===============================
# Main Function to Run Servers
# ===============================
async def main():
    # Start both WebSocket and SOCKS5 Proxy Server, and HTTP Proxy Server
    await asyncio.gather(
        websocket_server(),
        start_socks5_proxy_server(),
        start_http_proxy_server(),
    )

if __name__ == "__main__":
    asyncio.run(main())
