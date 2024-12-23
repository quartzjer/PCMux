# PCMux

A real-time media streaming protocol and toolkit for Python, based on JSON messages containing base64-encoded PCM audio and PNG image data. Perfect for building utility media applications like voice/video assistants, meeting tools, and streaming services.

## Features
- PCM audio and PNG image streaming over WebSocket or STDIO
- Support for 16-bit mono audio at 24kHz sampling rate
- Support for PNG images up to 1024px dimensions
- Compatible with OpenAI Realtime API format
- Multiple media sources: microphone, files, WebRTC (WHIP, OBS)
- Multiple sinks: speakers, files, transcription, web chat
- Recording and media capture capabilities

## Installation
1. Clone the repository
2. Install dependencies: `pip install -r requirements.txt`
3. Set up your OpenAI API key in .env: `OPENAI_API_KEY=your_key_here`

## Components

### Sources
- `source_mic.py` - Stream from microphone
- `source_webrtc.py` - Stream from a browser, includes screen sharing
- `source_file.py` - Stream from media files
- `source_whip.py` - Receive WebRTC streams from OBS

### Sinks
- `sink_speaker.py` - Play audio through speakers
- `sink_file.py` - Record to audio file
- `sink_transcribe.py` - Real-time transcription
- `sink_webchat.py` - Web interface with chat
- `sink_observe.py` - Meeting observer

### Pass-throughs
- `tee_record.py` - Record audio while passing through
- `tee_slides.py` - Detect and capture slides while passing through

## Usage Examples
Stream from file to speakers:
`python source_file.py input.mp3 | python sink_speaker.py`

See a real-time transcript using OpenAI's Realtime API while recording:
`python source_mic.py | python tee_record.py | python sink_transcript.py`

Start server for OBS and interact with the stream via a web chat interface powered by OpenAI:
`python source_whip.py | python sink_webchat.py`

## Message Format
Media data is sent as JSON messages:
`{"type": "pcmux.audio.delta", "delta": "<base64_encoded_pcm_data>"}`
`{"type": "pcmux.video.frame", "mime": "image/png", "data": "<base64_encoded_image_data>"}`

See [format.md](format.md) for complete protocol specification.

## License
Apache License 2.0 - See [LICENSE](LICENSE) file for details.