#!/usr/bin/env python3

import sys
import av
import json
import base64
import numpy as np

def create_audio_container(output_file):
    container = av.open(output_file, mode='w')
    format_name = output_file.split('.')[-1].lower()
    
    codec_name = {
        'mp3': 'mp3',
        'wav': 'pcm_s16le',
        'aac': 'aac',
        'ogg': 'libvorbis',
        'm4a': 'aac',
        'flac': 'flac'
    }.get(format_name, 'mp3')
    
    stream = container.add_stream(codec_name)
    stream.channels = 1
    stream.rate = 24000
    
    if codec_name == 'pcm_s16le':
        stream.format = 's16'
    
    return container, stream

def main():
    if len(sys.argv) != 2:
        print("Usage: sink_file.py <output_file>")
        sys.exit(1)

    try:
        container, stream = create_audio_container(sys.argv[1])
        frame = av.AudioFrame(format='s16', layout='mono', samples=512)
        frame.rate = 24000
        
        sample_buffer = np.array([], dtype=np.int16)
        
        for line in sys.stdin:
            try:
                message = json.loads(line)
                if message['type'] == 'pcmux.audio.delta':
                    new_samples = np.frombuffer(base64.b64decode(message['delta']), dtype=np.int16)
                    sample_buffer = np.append(sample_buffer, new_samples)
                    
                    while len(sample_buffer) >= 512:
                        frame_samples = sample_buffer[:512]
                        sample_buffer = sample_buffer[512:]
                        
                        frame.planes[0].update(frame_samples.tobytes())
                        for packet in stream.encode(frame):
                            container.mux(packet)
                
            except (json.JSONDecodeError, Exception) as e:
                print(f"Error: {e}", file=sys.stderr)
                continue
        
        if len(sample_buffer) > 0:
            frame_samples = np.pad(sample_buffer, (0, 512 - len(sample_buffer)))
            frame.planes[0].update(frame_samples.tobytes())
            for packet in stream.encode(frame):
                container.mux(packet)
        
        for packet in stream.encode(None):
            container.mux(packet)
            
        container.close()
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()