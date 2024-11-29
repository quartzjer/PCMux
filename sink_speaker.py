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

    try:
        for line in sys.stdin:
            message = json.loads(line)
            if message.get("type") == "pcmux.audio.delta":
                audio_data = base64.b64decode(message["delta"])
                stream.write(audio_data)
    except KeyboardInterrupt:
        pass
    finally:
        stream.stop_stream()
        stream.close()
        audio.terminate()

if __name__ == "__main__":
    main()
