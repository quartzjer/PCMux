#!/usr/bin/env python3

import sys
import av
import base64
import json

def main():
    if len(sys.argv) != 2:
        print("Usage: source_file.py <audio_file>")
        sys.exit(1)

    audio_file = sys.argv[1]
    container = av.open(audio_file)
    stream = container.streams.audio[0]

    resampler = av.AudioResampler(
        format='s16',
        layout='mono',
        rate=24000
    )

    for frame in container.decode(stream):
        resampled_frames = resampler.resample(frame)
        for resampled_frame in resampled_frames:
            audio_data = resampled_frame.to_ndarray().tobytes()
            encoded_data = base64.b64encode(audio_data).decode('utf-8')
            message = {
                "type": "pcmux.audio.delta",
                "delta": encoded_data
            }
            print(json.dumps(message))
            sys.stdout.flush()

if __name__ == "__main__":
    main()