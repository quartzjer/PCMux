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
import google.generativeai as genai
from io import BytesIO
import wave

load_dotenv()

WEBSOCKET_URL = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01"

INSTRUCTIONS = "Your task is to provide clear and accurate transcriptions of everything you hear in the audio. Focus on producing verbatim transcripts, including all spoken words and meaningful sounds. No other added commentary, just the transcript please."

interrupted = False

def signal_handler(sig, frame):
    global interrupted
    interrupted = True
    print("\nExiting...")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

class AudioReceiver:
    def __init__(self, ws, commit_interval=5, use_gemini=False):
        self.ws = ws
        self.thread = threading.Thread(target=self.receive_audio, daemon=True)
        self.running = False
        self.commit_interval = commit_interval
        self.last_commit_time = time.time()
        self.use_gemini = use_gemini
        self.audio_buffer = BytesIO()
        self.wav_writer = None

    def initialize_wav(self):
        self.audio_buffer = BytesIO()
        self.wav_writer = wave.open(self.audio_buffer, 'wb')
        self.wav_writer.setnchannels(1)
        self.wav_writer.setsampwidth(2)
        self.wav_writer.setframerate(44100)

    def process_with_gemini(self):
        if not self.wav_writer:
            return
        
        self.wav_writer.close()
        audio_bytes = self.audio_buffer.getvalue()
        
        try:
            model = genai.GenerativeModel('gemini-1.5-flash-8b')
            response = model.generate_content([
                INSTRUCTIONS,
                {
                    "mime_type": "audio/wav",
                    "data": audio_bytes
                }
            ])
            print(f"gemini: {response.text}")
        except Exception as e:
            print(f"Gemini API error: {e}")
        
        self.initialize_wav()

    def start(self):
        self.running = True
        self.thread.start()

    def receive_audio(self):
        if self.use_gemini:
            self.initialize_wav()
            
        try:
            for line in sys.stdin:
                if not self.running:
                    break
                message = json.loads(line)
                if message.get("type") == "pcmux.audio.delta":
                    audio_event = {"type": "input_audio_buffer.append", "audio": message["delta"]}
                    self.ws.send(json.dumps(audio_event))

                    if self.use_gemini:
                        audio_data = base64.b64decode(message["delta"])
                        self.wav_writer.writeframes(audio_data)

                    current_time = time.time()
                    if current_time - self.last_commit_time >= self.commit_interval:
                        self.ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
                        self.ws.send(json.dumps({"type": "response.create"}))
                        if self.use_gemini:
                            self.process_with_gemini()
                        self.last_commit_time = current_time
        except KeyboardInterrupt:
            pass

    def stop(self):
        self.running = False

class ChatStreaming:
    def __init__(self, api_key, verbose=False, commit_interval=5, use_gemini=False):
        self.api_key = api_key
        self.ws = None
        self.verbose = verbose
        self.audio_receiver = None
        self.commit_interval = commit_interval
        self.use_gemini = use_gemini

    def log(self, message):
        if self.verbose:
            print(f"[DEBUG] {message}")

    def on_open(self, ws):
        self.audio_receiver = AudioReceiver(ws, self.commit_interval, self.use_gemini)
        self.audio_receiver.start()
        session_update_message = {
            "type": "session.update",
            "session": {
                "modalities": ["text"],
                "instructions": INSTRUCTIONS,
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
    parser = argparse.ArgumentParser(description="Live transcriptions via streaming audio to OpenAI's GPT-4o model, whisper, and Gemini")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output")
    parser.add_argument("-c", "--commit-interval", type=float, default=5.0, 
                      help="How often to commit audio buffer in seconds (default: 5.0)")
    parser.add_argument("-g", "--gemini", action="store_true", help="Enable Gemini API for audio processing")
    args = parser.parse_args()

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY environment variable not set.")
        sys.exit(1)

    if args.gemini:
        gemini_key = os.getenv("GEMINI_API_KEY")
        if not gemini_key:
            print("Error: GEMINI_API_KEY environment variable not set.")
            sys.exit(1)
        genai.configure(api_key=gemini_key)

    chat = ChatStreaming(api_key, verbose=args.verbose, commit_interval=args.commit_interval, 
                        use_gemini=args.gemini)
    chat.run()

if __name__ == "__main__":
    main()
