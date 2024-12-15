# this doesn't work, too much hallucinated!
import os
import sys
import json
import time
import signal
import argparse
import base64
import wave
import logging

import numpy as np
import torch
from dotenv import load_dotenv
load_dotenv()

from faster_whisper import WhisperModel
import nemo.collections.asr as nemo_asr
from nemo.collections.asr.parts.utils.speaker_utils import perform_clustering

logging.basicConfig(stream=sys.stderr, level=logging.INFO, format='[%(levelname)s] %(message)s')
interrupted = False

def signal_handler(sig, frame):
    global interrupted
    interrupted = True
    logging.info("Interrupted, exiting...")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

class AudioProcessor:
    def __init__(self, commit_interval=5.0, verbose=False):
        self.commit_interval = commit_interval
        self.verbose = verbose
        if self.verbose:
            logging.getLogger().setLevel(logging.DEBUG)
        self.sample_rate = 16000
        self.audio_buffer = b""
        self.last_commit_time = time.time()
        self.vad_threshold = 0.5
        self.manifest_file = "online_manifest.json"

        model_path = os.getenv("WHISPER_MODEL_PATH", "medium.en")
        self.whisper_model = WhisperModel(model_path, device="cpu", compute_type="int8")

        # Load VAD and Speaker models
        self.vad_model = nemo_asr.models.EncDecClassificationModel.from_pretrained("vad_multilingual_marblenet").to("cuda" if torch.cuda.is_available() else "cpu")
        self.spk_model = nemo_asr.models.EncDecSpeakerLabelModel.from_pretrained("titanet_large").to("cuda" if torch.cuda.is_available() else "cpu")
        self.vad_model.eval()
        self.spk_model.eval()

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.AUDIO_RTTM_MAP = {}
        self.chunk_id = 0

    def append_audio(self, audio_bytes: bytes):
        self.audio_buffer += audio_bytes

    def create_manifest(self, audio_np: np.ndarray, chunk_id: int):
        audio_file_name = f"audio_chunk_{chunk_id}.wav"
        with wave.open(audio_file_name, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes((audio_np * 32768).astype(np.int16).tobytes())
        meta = {
            "audio_filepath": os.path.abspath(audio_file_name),
            "offset": 0.0,
            "duration": len(audio_np) / self.sample_rate
        }
        self.AUDIO_RTTM_MAP[f"audio_chunk_{chunk_id}"] = meta
        # Write a single-entry manifest
        with open(self.manifest_file, 'w') as f:
            json.dump(meta, f)
            f.write("\n")
    
    def get_speech_segments(self, audio_np: np.ndarray):
        # VAD expects (batch, time), we have a single segment so just [1, T]
        audio_torch = torch.from_numpy(audio_np).float().to(self.vad_model.device)
        audio_len = torch.tensor([audio_torch.shape[0]]).to(self.vad_model.device)

        with torch.no_grad():
            # The VAD model returns logits directly.
            vad_res = self.vad_model(input_signal=audio_torch.unsqueeze(0), input_signal_length=audio_len)

        logging.debug(f"VAD result: {vad_res}")
        # vad_res shape is [1, 2], apply softmax to get speech probability
        speech_prob = torch.softmax(vad_res, dim=-1)[0,1].item()

        segments = []
        if speech_prob > self.vad_threshold:
            # If above threshold, consider the entire chunk as speech
            segments.append((0, len(audio_np) / self.sample_rate))
        return segments

    def process_audio_chunk(self):
        if not self.audio_buffer:
            return
        try:
            audio_np = np.frombuffer(self.audio_buffer, dtype=np.int16).astype(np.float32) / 32768.0
        except ValueError as e:
            logging.error(f"Error decoding audio buffer: {e}")
            self.audio_buffer = b""
            return

        if len(audio_np) == 0:
            self.audio_buffer = b""
            return

        self.create_manifest(audio_np, self.chunk_id)
        segments = self.get_speech_segments(audio_np)
        if not segments:
            # No speech detected
            self.audio_buffer = b""
            self.chunk_id += 1
            return

        # Extract speaker embeddings
        embeddings = {f"audio_chunk_{self.chunk_id}": []}
        timestamps = {f"audio_chunk_{self.chunk_id}": []}

        meta = self.AUDIO_RTTM_MAP[f"audio_chunk_{self.chunk_id}"]
        start_sample = int(meta['offset'] * self.sample_rate)
        end_sample = int((meta['offset'] + meta['duration']) * self.sample_rate)
        seg_audio = audio_np[start_sample:end_sample]

        if len(seg_audio) > 0:
            # Speaker model expects shape [B, T]
            audio_torch = torch.from_numpy(seg_audio).float().to(self.spk_model.device).unsqueeze(0)
            audio_len = torch.tensor([audio_torch.shape[-1]]).to(self.spk_model.device)

            with torch.no_grad():
                # The speaker model returns a tuple of (logits, embeddings)
                spk_model_output = self.spk_model(input_signal=audio_torch, input_signal_length=audio_len)
                logging.debug(f"Speaker model: {spk_model_output}")
                emb = spk_model_output[1].cpu().numpy()  # Use the second tensor (embeddings)

            embeddings[f"audio_chunk_{self.chunk_id}"].append(emb[0])
            timestamps[f"audio_chunk_{self.chunk_id}"].append([meta['offset'], meta['offset'] + meta['duration']])

        if len(embeddings[f"audio_chunk_{self.chunk_id}"]) > 0:
            embeddings_array = np.concatenate(embeddings[f"audio_chunk_{self.chunk_id}"], axis=0)
            timestamps_array = np.array(timestamps[f"audio_chunk_{self.chunk_id}"])
            embs_and_timestamps = {
                f"audio_chunk_{self.chunk_id}": {
                    'embeddings': torch.from_numpy(embeddings_array),
                    'timestamps': torch.from_numpy(timestamps_array),
                    'multiscale_segment_counts': torch.tensor([len(embeddings[f"audio_chunk_{self.chunk_id}"])])
                }
            }
        else:
            embs_and_timestamps = {}

        # Perform clustering and transcription if we have embeddings
        if embs_and_timestamps:
            all_reference, all_hypothesis = perform_clustering(
                embs_and_timestamps=embs_and_timestamps,
                AUDIO_RTTM_MAP=self.AUDIO_RTTM_MAP,
                out_rttm_dir=None,
                clustering_params={
                    "max_num_speakers": 8,
                    "oracle_num_speakers": False,
                    "max_rp_threshold": 0.9,
                    "sparse_search_volume": 30,
                    "enhance_count_threshold": 3
                },
                device=torch.device(self.device),
                verbose=self.verbose
            )

            for uniq_id, annotation in all_hypothesis:
                for segment, speaker in annotation.itertracks(yield_label=True):
                    start_sample = int(segment.start * self.sample_rate)
                    end_sample = int(segment.end * self.sample_rate)
                    segment_audio = audio_np[start_sample:end_sample]
                    # Skip very short segments
                    if len(segment_audio) < self.sample_rate * 0.1:
                        continue
                    transcription = self.transcribe_array(segment_audio)
                    if transcription.strip():
                        event = {
                            "type": "pcmux.text.chunk",
                            "speaker": speaker,
                            "text": transcription
                        }
                        print(json.dumps(event))
                        sys.stdout.flush()

        self.audio_buffer = b""
        self.chunk_id += 1

    def transcribe_array(self, audio_np: np.ndarray) -> str:
        segments, _ = self.whisper_model.transcribe(audio_np, beam_size=1, language="en")
        return " ".join([seg.text for seg in segments]).strip()

    def maybe_commit(self):
        # Commit at intervals to process buffered audio
        if time.time() - self.last_commit_time >= self.commit_interval:
            self.process_audio_chunk()
            self.last_commit_time = time.time()

def main():
    parser = argparse.ArgumentParser(description="Local streaming transcription.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output")
    parser.add_argument("-c", "--commit-interval", type=float, default=5.0,
                        help="How often to commit audio buffer in seconds (default: 5.0)")
    args = parser.parse_args()

    processor = AudioProcessor(commit_interval=args.commit_interval, verbose=args.verbose)
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
        if message.get("type", "") == "pcmux.audio.delta":
            audio_b64 = message.get("delta", "")
            if audio_b64:
                processor.append_audio(base64.b64decode(audio_b64))
                processor.maybe_commit()
    # Process any remaining audio after the loop
    processor.process_audio_chunk()

if __name__ == "__main__":
    main()
