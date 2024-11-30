#!/usr/bin/env python3

import sys
import av
import base64
import json
import time

def main():
    if len(sys.argv) < 2 or len(sys.argv) > 3:
        print("Usage: source_file.py <audio_file> [playback_rate]")
        sys.exit(1)

    audio_file = sys.argv[1]
    playback_rate = float(sys.argv[2]) if len(sys.argv) == 3 else None

    container = av.open(audio_file)
    stream = container.streams.audio[0]

    sample_rate = 24000
    resampler = av.AudioResampler(
        format='s16',
        layout='mono',
        rate=sample_rate
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
            if playback_rate:
                frame_duration = resampled_frame.samples / sample_rate
                time.sleep(frame_duration / playback_rate)

if __name__ == "__main__":
    main()