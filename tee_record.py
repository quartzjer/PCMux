import sys
import json
import base64
import os
import argparse
import logging
from datetime import datetime

import av
import numpy as np

def parse_arguments():
    parser = argparse.ArgumentParser(description='Smart Tee Record Application')
    parser.add_argument('directory', type=str, nargs='?', default=os.getcwd(), help='Target directory for saving recordings (default: current working directory)')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose debugging')
    return parser.parse_args()

def setup_logging(verbose):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format='%(asctime)s - %(levelname)s - %(message)s', stream=sys.stderr)

def ensure_directory(directory):
    os.makedirs(directory, exist_ok=True)

def create_audio_container(output_file):
    container = av.open(output_file, mode='w')
    stream = container.add_stream('mp3')
    stream.channels = 1
    stream.rate = 24000
    return container, stream

def main():
    args = parse_arguments()
    setup_logging(args.verbose)
    ensure_directory(args.directory)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = os.path.join(args.directory, f'{timestamp}.mp3')
    
    try:
        container, stream = create_audio_container(output_file)
        frame = av.AudioFrame(format='s16', layout='mono', samples=512)
        frame.rate = 24000
        
        sample_buffer = np.array([], dtype=np.int16)
        
        for line in sys.stdin:
            # Pass all messages through
            print(line, end='', flush=True)
            
            try:
                message = json.loads(line)
                if message.get('type') == 'pcmux.audio.delta':
                    new_samples = np.frombuffer(base64.b64decode(message['delta']), dtype=np.int16)
                    sample_buffer = np.append(sample_buffer, new_samples)
                    
                    while len(sample_buffer) >= 512:
                        frame_samples = sample_buffer[:512]
                        sample_buffer = sample_buffer[512:]
                        
                        frame.planes[0].update(frame_samples.tobytes())
                        for packet in stream.encode(frame):
                            container.mux(packet)
                            
            except json.JSONDecodeError:
                logging.error("Failed to decode JSON from input")
                continue
            except Exception as e:
                logging.error(f"Error processing audio: {e}")
                continue

        # Flush remaining samples
        if len(sample_buffer) > 0:
            frame_samples = np.pad(sample_buffer, (0, 512 - len(sample_buffer)))
            frame.planes[0].update(frame_samples.tobytes())
            for packet in stream.encode(frame):
                container.mux(packet)
        
        # Flush encoder
        for packet in stream.encode(None):
            container.mux(packet)
            
        container.close()
        logging.info(f"Recording saved: {output_file}")
        
    except Exception as e:
        logging.error(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
