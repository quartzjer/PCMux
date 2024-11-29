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
    stream = audio.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)

    try:
        while True:
            data = stream.read(CHUNK)
            encoded_data = base64.b64encode(data).decode('utf-8')
            message = {
                "type": "pcmux.audio.delta",
                "delta": encoded_data
            }
            print(json.dumps(message))
            sys.stdout.flush()
    except KeyboardInterrupt:
        pass
    finally:
        stream.stop_stream()
        stream.close()
        audio.terminate()

if __name__ == "__main__":
    main()
