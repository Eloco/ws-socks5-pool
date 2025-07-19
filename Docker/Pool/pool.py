#!/usr/bin/env python
# coding=utf-8

import asyncio
import websockets
import json
import requests
import base64
import traceback
import uuid
import pickle

def encrypt_binary_to_string(binary_data):
    return base64.b64encode(binary_data).decode('utf-8')
def decrypt_string_to_binary(encoded_string):
    return base64.b64decode(encoded_string)


# 获取代理端的 IP 和区域（通过请求 ipinfo.io）
def get_ip_info():
    sid = str(uuid.uuid4())
    try:
        response = requests.get("https://ipinfo.io/json")
        data = response.json()
        ip = data.get("ip", "unknown")
        region = data.get("region", "unknown")
        country = data.get("country", "unknown")
        return country, ip, region, sid
    except requests.RequestException as e:
        print(f"Error fetching IP info: {e}")
        return "unknown", "unknown", "unknown",sid


# Store reader and writer mappings for different client IDs
client_connections = {}

import os
if not (websocket_server_addr := os.getenv('websocket_server_addr')):
    websocket_server_addr = "ws://localhost:8765"


async def start_websocket_server():
    """Start WebSocket server."""
    uri = websocket_server_addr
    async with websockets.connect(uri) as websocket:
        try:
            # Get proxy information
            country, ip, region, sid = get_ip_info()
            registration_data = {
                "country": country,
                "ip": ip,
                "region": region,
                "sid": sid,
            }
            await websocket.send(json.dumps(registration_data))
            print(f"Proxy {ip} registered in region: {region}")
        except Exception as e:
            print(f"Error in proxy handler: {e}")

        try:
            while True:
                # Receive WebSocket message
                binary_data = await websocket.recv()
                data = pickle.loads(binary_data)
                message = data.get("data", {})
                print("received ws_message",message[:10])
                client_id = data.get("client_id")
                # print(f"Client ID: {client_id}")

                # If no message, skip to the next iteration
                if not message:
                    print("No message received, waiting...")
                    await asyncio.sleep(1)
                    continue

                # If the message is "eof", handle disconnection
                if message == b"eof":
                    print(f"Connection closed by client {client_id}")
                    if client_id in client_connections:
                        reader, writer = client_connections[client_id]
                        writer.close()
                        del client_connections[client_id]
                    continue

                # Check if the reader and writer exist for this client
                if client_id not in client_connections:
                    # Establish a new connection for this client_id
                    reader, writer = await asyncio.open_connection('localhost', 1088)
                    client_connections[client_id] = (reader, writer)

                # Retrieve the reader and writer for this client_id
                reader, writer = client_connections[client_id]

                # Send the received message to the client
                print(f"Sending message to client {client_id}")
                print("write_to_socks5_server",message)
                writer.write(message)
                await writer.drain()

                # Read data from the SOCKS5 server
                try:
                    # client_data = await asyncio.wait_for(reader.read(4096), timeout=5.0)
                    client_data=b""
                    count=0
                    while True:
                        count+=1
                        chunk = await asyncio.wait_for(reader.read(4096), timeout=1)
                        print(len(chunk))
                        # if len(chunk) < 4096:
                        #     break
                        if not chunk:
                            break
                        else:
                            client_data += chunk
                            if client_data[0] == 5:
                                break
                except:
                    print(f"Error: timeout will send 'eof'")
                finally:
                    if not client_data:
                        print(f"No data received for client {client_id}, waiting...")
                        writer.close()
                        del client_connections[client_id]
                        client_data = b"eof"

                # Send back the server data to the WebSocket client
                print("send_back_to_client",client_data)
                client_data = encrypt_binary_to_string(client_data)
                await websocket.send(client_data)

        except Exception as e:
            print(f"Error in proxy handler: {e}")
            traceback.print_exc()

        finally:
            print(f"Proxy disconnected.")


async def main():
    await start_websocket_server()

if __name__ == "__main__":
    asyncio.run(main())
