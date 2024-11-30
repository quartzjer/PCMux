import os
import sys
import json
import asyncio
import aiohttp
from aiohttp import web
from dotenv import load_dotenv
import datetime

load_dotenv()

WEBSOCKET_URL = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01"

def timestamp():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

class OpenAIWSManager:
    def __init__(self):
        self.ws = None

    async def get_ws(self):
        return self.ws

    def set_ws(self, ws):
        self.ws = ws

async def handle_index(request):
    return web.FileResponse('./sink_webchat.html')

async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    print(f"[{timestamp()}] New client WebSocket connection established")
    request.app['websockets'].add(ws)
    try:
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                data = json.loads(msg.data)
                openai_ws = await request.app['ws_manager'].get_ws()
                if openai_ws:
                    await openai_ws.send_json(data)
                    print(f"[{timestamp()}] Message forwarded to OpenAI: {data['type']}")
    finally:
        request.app['websockets'].discard(ws)
        print(f"[{timestamp()}] Client WebSocket connection closed")
    return ws

async def openai_handler(app):
    print(f"[{timestamp()}] Initiating OpenAI WebSocket connection")
    headers = {
        "Authorization": f"Bearer {app['api_key']}",
        "OpenAI-Beta": "realtime=v1"
    }
    ws_manager = app['ws_manager']
    
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(WEBSOCKET_URL, headers=headers) as ws_openai:
            ws_manager.set_ws(ws_openai)
            session_update_message = {
                "type": "session.update",
                "session": {
                    "modalities": ["text"],
                    "instructions": "You are listening to a meeting, your job is to pay attention and wait for a text message from another listener then respond specifically to that request.",
                    "temperature": 0.7,
                    "input_audio_transcription": {
                        "model": "whisper-1"
                    },
                    "turn_detection": None,
                    "max_response_output_tokens": 500
                }
            }
            await ws_openai.send_json(session_update_message)

            async def read_stdin():
                print(f"[{timestamp()}] Starting stdin reader")
                loop = asyncio.get_running_loop()
                while True:
                    line = await loop.run_in_executor(None, sys.stdin.readline)
                    if not line:
                        break
                    message = json.loads(line)
                    if message.get("type") == "pcmux.audio.delta":
                        audio_event = {
                            "type": "input_audio_buffer.append",
                            "audio": message["delta"]
                        }
                        await ws_openai.send_json(audio_event)
                        # Relay summary audio events to web clients
                        for client_ws in app['websockets']:
                            await client_ws.send_json({
                                "type": "input_audio_buffer.appended",
                                "length": len(message["delta"])
                            })

            async def openai_listener():
                print(f"[{timestamp()}] Starting OpenAI event listener")
                async for msg in ws_openai:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        event = json.loads(msg.data)
                        # Relay OpenAI events to all connected clients
                        for client_ws in app['websockets']:
                            await client_ws.send_json(event)
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        print(f'OpenAI WebSocket error: {ws_openai.exception()}')
                        break

            await asyncio.gather(read_stdin(), openai_listener())

async def on_startup(app):
    app['websockets'] = set()
    app['ws_manager'] = OpenAIWSManager()
    app['openai_task'] = asyncio.create_task(openai_handler(app))

async def on_shutdown(app):
    try:
        # Create a copy of the websockets set
        websockets = set(app['websockets'])
        for ws in websockets:
            await ws.close()
        
        openai_ws = await app['ws_manager'].get_ws()
        if openai_ws and not openai_ws.closed:
            await openai_ws.close()
        
        if not app['openai_task'].done():
            app['openai_task'].cancel()
            try:
                await app['openai_task']
            except asyncio.CancelledError:
                pass
    except Exception as e:
        print(f"Error during shutdown: {e}")

def main():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY environment variable not set.")
        sys.exit(1)

    app = web.Application()
    app['api_key'] = api_key
    app.add_routes([
        web.get('/', handle_index),
        web.get('/ws', websocket_handler),
        web.get('/favicon.ico', lambda request: web.Response(status=204)),
    ])
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    web.run_app(app, port=8088)

if __name__ == "__main__":
    main()
