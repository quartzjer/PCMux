import pyaudio
import base64
import json
import sys

# Audio configuration
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 24000
CHUNK = 1024

def main():
    audio = pyaudio.PyAudio()
    stream = audio.open(format=FORMAT, channels=CHANNELS, rate=RATE, output=True, frames_per_buffer=CHUNK)
    buffer = bytearray()

    try:
        for line in sys.stdin:
            message = json.loads(line)
            if message.get("type") == "pcmux.audio.delta":
                audio_data = base64.b64decode(message["delta"])
                buffer.extend(audio_data)
                
                while len(buffer) >= CHUNK * 2:
                    chunk = buffer[:CHUNK * 2]
                    buffer = buffer[CHUNK * 2:]
                    stream.write(bytes(chunk))
    except KeyboardInterrupt:
        pass
    finally:
        if buffer:
            stream.write(bytes(buffer))
        stream.stop_stream()
        stream.close()
        audio.terminate()

if __name__ == "__main__":
    main()
