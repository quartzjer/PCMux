# PCMux

A real-time audio streaming protocol and toolkit for Python, based on JSON messages containing base64-encoded PCM audio data. Perfect for building utility audio applications like voice assistants, meeting tools, and streaming services.

## Features
- PCM audio streaming over WebSocket or STDIO
- Support for 16-bit mono audio at 24kHz sampling rate
- Compatible with OpenAI Realtime API format
- Multiple audio sources: microphone, files, WebRTC (WHIP, OBS)
- Multiple sinks: speakers, files, transcription, web chat
- Recording and slide capture capabilities

## Installation
1. Clone the repository
2. Install dependencies: `pip install -r requirements.txt`
3. Set up your OpenAI API key in .env: `OPENAI_API_KEY=your_key_here`

## Components

### Sources
- `source_mic.py` - Stream from microphone
- `source_file.py` - Stream from audio files
- `source_whip.py` - Receive WebRTC streams from OBS

### Sinks
- `sink_speaker.py` - Play audio through speakers
- `sink_file.py` - Record to audio file
- `sink_transcribe.py` - Real-time transcription
- `sink_webchat.py` - Web interface with chat
- `sink_observe.py` - Meeting observer

### Pass-throughs
- `tee_record.py` - Record while passing through
- `tee_slides.py` - Capture slides while passing through

## Usage Examples
Stream from file to speakers:
`python source_file.py input.mp3 | python sink_speaker.py`

See a real-time transcript using OpenAI's Realtime API while recording:
`python source_mic.py | python tee_record.py | python sink_transcript.py`

Start server for OBS and interact with the stream via a web chat interface powered by OpenAI:
`python source_whip.py | python sink_webchat.py`

## Message Format
Audio data is sent as JSON messages:
`{"type": "pcmux.audio.delta", "delta": "<base64_encoded_pcm_data>"}`

See [format.md](format.md) for complete protocol specification.

## License
Apache License 2.0 - See [LICENSE](LICENSE) file for details.