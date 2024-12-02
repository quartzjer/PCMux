#!/usr/bin/env python3

import sys
import av
import base64
import json
import time
import io
import logging
import argparse

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(description='Stream media file to PCMux protocol')
    parser.add_argument('media_file', help='Path to media file to stream')
    parser.add_argument('--playback-rate', type=float, default=1.0,
                       help='Playback rate multiplier (default: 1.0)')
    args = parser.parse_args()

    try:
        container = av.open(args.media_file)
    except Exception as e:
        logger.error(f"Failed to open media file: {e}")
        sys.exit(1)

    sample_rate = 24000
    logger.info(f"Opening media file: {args.media_file}")

    # Determine if file has audio and/or video streams
    audio_stream = None
    video_stream = None
    for stream in container.streams:
        if stream.type == 'audio' and audio_stream is None:
            audio_stream = stream
        elif stream.type == 'video' and video_stream is None:
            video_stream = stream

    if audio_stream:
        logger.info(f"Found audio stream with {audio_stream.codec_context.sample_rate}Hz")
        audio_resampler = av.AudioResampler(
            format='s16',
            layout='mono',
            rate=sample_rate
        )

    if video_stream:
        logger.info(f"Found video stream with {video_stream.average_rate}fps")
        SCREEN_MAX = 1024
        FRAME_INTERVAL = int(max(1, video_stream.average_rate / 30))
        frame_counter = 0

    if not audio_stream and not video_stream:
        logger.error("No audio or video streams found in the file")
        sys.exit(1)

    try:
        for packet in container.demux():
            if packet.stream == audio_stream:
                for frame in packet.decode():
                    # Handle audio frame
                    resampled_frames = audio_resampler.resample(frame)
                    for resampled_frame in resampled_frames:
                        audio_data = resampled_frame.to_ndarray().tobytes()
                        encoded_data = base64.b64encode(audio_data).decode('utf-8')
                        message = {
                            "type": "pcmux.audio.delta",
                            "delta": encoded_data
                        }
                        print(json.dumps(message))
                        sys.stdout.flush()
                        if args.playback_rate != 1.0:
                            frame_duration = resampled_frame.samples / sample_rate
                            time.sleep(frame_duration / args.playback_rate)
            elif packet.stream == video_stream:
                for frame in packet.decode():
                    # Handle video frame
                    frame_counter += 1
                    if frame_counter % FRAME_INTERVAL == 0:
                        logger.debug(f"Processing video frame {frame_counter}")
                        img = frame.to_image()
                        if img.width > SCREEN_MAX or img.height > SCREEN_MAX:
                            img.thumbnail((SCREEN_MAX, SCREEN_MAX), resample=3)
                        img_byte_arr = io.BytesIO()
                        img.save(img_byte_arr, format='PNG')
                        img_base64 = base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')
                        message = {
                            "type": "stream.image.snapshot",
                            "mime": "image/png",
                            "data": img_base64
                        }
                        print(json.dumps(message))
                        sys.stdout.flush()
                    if args.playback_rate != 1.0:
                        frame_duration = 1 / float(video_stream.average_rate)
                        time.sleep(frame_duration / args.playback_rate)
    except KeyboardInterrupt:
        logger.info("Streaming interrupted by user")
    except Exception as e:
        logger.error(f"Error during streaming: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()