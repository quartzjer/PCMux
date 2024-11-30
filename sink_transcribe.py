import os
import json
import threading
import websocket
import sys
import signal
import time
from dotenv import load_dotenv
import argparse
import base64

load_dotenv()

WEBSOCKET_URL = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01"

interrupted = False

def signal_handler(sig, frame):
    global interrupted
    interrupted = True
    print("\nExiting...")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

class AudioReceiver:
    def __init__(self, ws, commit_interval=5):
        self.ws = ws
        self.thread = threading.Thread(target=self.receive_audio, daemon=True)
        self.running = False
        self.commit_interval = commit_interval
        self.last_commit_time = time.time()

    def start(self):
        self.running = True
        self.thread.start()

    def receive_audio(self):
        try:
            for line in sys.stdin:
                if not self.running:
                    break
                message = json.loads(line)
                if message.get("type") == "pcmux.audio.delta":
                    
                    audio_event = {"type": "input_audio_buffer.append", "audio": message["delta"]}
                    self.ws.send(json.dumps(audio_event))

                    current_time = time.time()
                    if current_time - self.last_commit_time >= self.commit_interval:
                        self.ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
                        self.ws.send(json.dumps({"type": "response.create"}))
                        self.last_commit_time = current_time
        except KeyboardInterrupt:
            pass

    def stop(self):
        self.running = False

class ChatStreaming:
    def __init__(self, api_key, verbose=False, commit_interval=5):
        self.api_key = api_key
        self.ws = None
        self.verbose = verbose
        self.audio_receiver = None
        self.commit_interval = commit_interval

    def log(self, message):
        if self.verbose:
            print(f"[DEBUG] {message}")

    def on_open(self, ws):
        self.audio_receiver = AudioReceiver(ws, self.commit_interval)
        self.audio_receiver.start()
        session_update_message = {
            "type": "session.update",
            "session": {
                "modalities": ["text"],
                "instructions": "Your task is to provide clear and accurate transcriptions of everything you hear in the audio. Focus on producing verbatim transcripts, including all spoken words and meaningful sounds. No other added commentary, just the transcript please.",
                "temperature": 0.7,
                "input_audio_transcription": {
                    "model": "whisper-1"
                },
                "max_response_output_tokens": 500
            }
        }
        ws.send(json.dumps(session_update_message))

    def on_message(self, ws, message):
        try:
            event = json.loads(message)
            event_type = event.get("type")
            if event_type == "response.done":
                output = event.get("response", {}).get("output", [])
                if output:
                    content = output[0].get("content", [])
                    if content:
                        response_text = content[0].get("text", "")
                        print(f"gpt4o: {response_text}")
            elif event_type == "session.created":
                print("Session started.")
            elif event_type == "conversation.item.input_audio_transcription.completed":
                transcript = event.get("transcript", "")
                print(f"whisper: {transcript}")
            elif event_type == "error":
                print(f"Error: {event.get('error', {}).get('message')}")
            elif event_type.startswith("input_audio_buffer.") or event_type.startswith("conversation.") or event_type.startswith("response.") or event_type == "session.updated" or event_type == "rate_limits.updated":
                None
            else:
                self.log(f"Unhandled event type: {event_type} {json.dumps(event)}")
        except json.JSONDecodeError:
            print("Received non-JSON message.")
        except Exception as e:
            print(f"Exception in on_message: {e} for event {json.dumps(event)}")

    def on_error(self, ws, error):
        print(f"WebSocket error: {error}")
        self.log(f"WebSocket error: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        print("WebSocket connection closed.")
        self.log(f"WebSocket closed with code {close_status_code}, message: {close_msg}")
        if self.audio_receiver:
            self.audio_receiver.stop()

    def run(self):
        headers = {"Authorization": f"Bearer {self.api_key}", "OpenAI-Beta": "realtime=v1"}
        self.ws = websocket.WebSocketApp(
            WEBSOCKET_URL,
            header=headers,
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close
        )
        self.ws.run_forever()

def main():
    parser = argparse.ArgumentParser(description="OpenAI Chat Passive Observer with PCMUX Audio Streaming")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
    parser.add_argument("--commit-interval", type=float, default=5.0, 
                      help="How often to commit audio buffer in seconds (default: 5.0)")
    args = parser.parse_args()

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY environment variable not set.")
        sys.exit(1)

    chat = ChatStreaming(api_key, verbose=args.verbose, commit_interval=args.commit_interval)
    chat.run()

if __name__ == "__main__":
    main()
