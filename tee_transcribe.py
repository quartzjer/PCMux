import os
import sys
import json
import time
import signal
import argparse
import base64
import wave
import logging
import io

import numpy as np
import torch
from dotenv import load_dotenv

# For local STT:
# Faster Whisper: https://github.com/guillaumekln/faster-whisper
from faster_whisper import WhisperModel

# For VAD and speaker detection:
# Pyannote Audio: https://github.com/pyannote/pyannote-audio
# We assume pre-trained models are available locally or via huggingface.
from pyannote.audio import Pipeline

load_dotenv()

# Set up logging to stderr
logging.basicConfig(stream=sys.stderr, level=logging.DEBUG, format='[%(levelname)s] %(message)s')

interrupted = False

def signal_handler(sig, frame):
    global interrupted
    interrupted = True
    logging.info("Interrupted, exiting...")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)


class AudioProcessor:
    def __init__(self, commit_interval=5.0, verbose=False, sample_rate=16000):
        self.commit_interval = commit_interval
        self.verbose = verbose
        self.sample_rate = sample_rate

        # Buffer to store audio data between commits
        self.audio_buffer = io.BytesIO()
        self.wav_writer = None
        self.last_commit_time = time.time()

        # Initialize local STT (Faster Whisper) and pyannote pipelines
        # Load a Whisper model (change model size/path as needed)
        model_path = os.getenv("WHISPER_MODEL_PATH", "medium.en")
        self.whisper_model = WhisperModel(
            model_path, 
            device="cpu", 
            compute_type="int8"
        )

        # Pyannote pipeline for speaker diarization (may require a pretrained model)
        # You may need to specify the exact pipeline here, for example:
        # pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization")
        # If you have a custom local pipeline:
        diarization_model = os.getenv("DIARIZATION_MODEL", "pyannote/speaker-diarization")
        self.diarization_pipeline = Pipeline.from_pretrained(diarization_model)

        self.initialize_wav()

    def initialize_wav(self):
        if self.wav_writer is not None:
            self.wav_writer.close()
        self.audio_buffer = io.BytesIO()
        self.wav_writer = wave.open(self.audio_buffer, 'wb')
        self.wav_writer.setnchannels(1)
        self.wav_writer.setsampwidth(2)
        self.wav_writer.setframerate(self.sample_rate)

    def append_audio(self, audio_bytes: bytes):
        self.wav_writer.writeframes(audio_bytes)

    def process_audio_chunk(self):
        # Close writer to finalize the WAV
        self.wav_writer.close()
        raw_audio = self.audio_buffer.getvalue()

        # Convert to numpy array and then to torch tensor for pyannote
        with wave.open(io.BytesIO(raw_audio), 'rb') as wf:
            n_samples = wf.getnframes()
            audio_data = wf.readframes(n_samples)
            audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
            # Convert to torch tensor and reshape for pyannote (channels, samples)
            audio_tensor = torch.from_numpy(audio_np).unsqueeze(0)

        # Run speaker diarization with torch tensor
        file = {"waveform": audio_tensor, "sample_rate": self.sample_rate}
        diarization_result = self.diarization_pipeline(file)
        # diarization_result is a pyannote.core.Annotation with speaker segments

        # Now we have annotated speaker segments. We'll iterate over them,
        # extract each segment, run STT on that segment, and print results.
        # Sort by time
        segments = list(diarization_result.itertracks(yield_label=True))
        segments.sort(key=lambda x: x[0].start)

        for segment, _, speaker in segments:
            # Extract segment
            start_sample = int(segment.start * self.sample_rate)
            end_sample = int(segment.end * self.sample_rate)
            segment_audio = audio_np[start_sample:end_sample]

            if len(segment_audio) == 0:
                continue

            # Transcribe using faster-whisper
            # Transcribe returns segments with text
            # We'll just do a single call with the segment since it's short
            # The model can handle numpy arrays directly if we provide them as float32.
            # The whisper model's transcribe method typically expects a file, so we might need
            # to pass raw audio. The faster-whisper's transcribe function can take a path
            # or use `buffer` parameter. Let's write a small helper function that 
            # transcribes from a numpy array.

            transcription = self.transcribe_array(segment_audio)
            if transcription.strip():
                # Print event in JSON
                event = {
                    "type": "pcmux.text.chunk",
                    "speaker": speaker,
                    "text": transcription
                }
                print(json.dumps(event))
                sys.stdout.flush()

        # Re-initialize for the next chunk
        self.initialize_wav()

    def transcribe_array(self, audio_np: np.ndarray) -> str:
        # The faster-whisper model's transcribe expects a path or audio as array.
        # According to the documentation, we can pass NumPy arrays directly:
        # transcribe(self, audio: Union[str, np.ndarray], **kwargs)
        # We'll use a low latency approach by passing the raw array.

        # We might want to use a small decoder options. If language is known, specify it.
        segments, _ = self.whisper_model.transcribe(audio_np, beam_size=1, language="en")
        # Combine text from all segments
        text = " ".join([seg.text for seg in segments])
        return text.strip()

    def maybe_commit(self):
        current_time = time.time()
        if current_time - self.last_commit_time >= self.commit_interval:
            # Process current chunk
            self.process_audio_chunk()
            self.last_commit_time = current_time


def main():
    parser = argparse.ArgumentParser(description="Local streaming transcription with pyannote for diarization and faster-whisper for STT.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output")
    parser.add_argument("-c", "--commit-interval", type=float, default=5.0,
                        help="How often to commit audio buffer in seconds (default: 5.0)")
    parser.add_argument("--sample-rate", type=int, default=16000, help="Sample rate for processing audio")
    args = parser.parse_args()

    processor = AudioProcessor(commit_interval=args.commit_interval, verbose=args.verbose, sample_rate=args.sample_rate)

    # Read from stdin line by line, expecting JSON messages with type "pcmux.audio.delta"
    for line in sys.stdin:
        if interrupted:
            break
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            logging.debug("Received non-JSON message.")
            continue

        mtype = message.get("type", "")
        if mtype == "pcmux.audio.delta":
            audio_b64 = message.get("delta", "")
            if audio_b64:
                audio_bytes = base64.b64decode(audio_b64)
                processor.append_audio(audio_bytes)
                processor.maybe_commit()
        else:
            # Ignore other message types or handle them if needed
            pass

    # Final flush
    processor.process_audio_chunk()


if __name__ == "__main__":
    main()