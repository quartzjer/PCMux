# PCMux - JSON-Based Real-Time Media Streaming Protocol

## Overview

This protocol defines a minimal structure for real-time media streaming over WebSocket connections and STDIO using JSON messages containing base64-encoded PCM audio data and image frames. It facilitates the transmission of audio and video data between applications in real-time, suitable for applications like live audio feeds, voice assistants, streaming services, and multimedia applications.

It is entirely derivative of and based on the [OpenAI Realtime API](https://platform.openai.com/docs/guides/realtime). This is just a minimal subset to support custom media streaming applications that want to maximize compatibility with the Realtime API.

## WebSocket Connection

Messages can be sent over a standard WebSocket connection. This specification defines multiple event types to carry audio and video over that socket. Other event types can be used for application-specific needs.

## STDIO Pipes

Messages can be piped between command line applications via STDIN and STDOUT. The JSON messages must not be formatted since each message is terminated by a newline, sometimes referred to as newline-delimited JSON (nd-json) or JSON Lines.

## Media Encoding Specifications

### Audio Encoding

- **Format**: PCM (Pulse-Code Modulation)
- **Sample Format**: 16-bit signed integers (`paInt16`)
- **Channels**: Mono (1 channel)
- **Sampling Rate**: 24,000 Hz
- **Chunk Size**: Variable
- **Bit Depth**: 16 bits per sample
- **Byte Order**: Little-endian
- **Data Rate**: For mono audio at 24 kHz, the data rate is 48,000 bytes per second (24,000 samples/sec × 2 bytes/sample).

PCM audio data is base64-encoded before being embedded in JSON messages.

### Video Encoding

- **Format**: PNG Images
- **Mime Type**: `image/png`
- **Resolution**: Variable, with a maximum dimension of 1024 pixels for either width or height. Images exceeding this size should be downscaled while maintaining aspect ratio.
- **Frame Rate**: One frame per second for analysis-oriented applications, not intended for video playback.

Image frame data is base64-encoded before being embedded in JSON messages.

## Message Transport

### Message Structure

All messages are JSON objects terminated by a newline character. Each message contains a `"type"` field that indicates the event type, along with other fields specific to that event.

```json
{
  "type": "<event_type>",
  "...": "other_fields_specific_to_event"
}
```

### Event Definitions

#### Common Fields

- **`type`**: String indicating the event type (e.g., `"pcmux.audio.delta"`, `"pcmux.video.frame"`).
- **`...`**: All other fields are specific to the event type.

#### `pcmux.audio.delta` Event

- **Type**: `"pcmux.audio.delta"`
- **Field**: `"delta"` contains the base64-encoded PCM audio data.

**Message Structure:**

```json
{
  "type": "pcmux.audio.delta",
  "delta": "<base64_encoded_pcm_data>"
}
```

#### `pcmux.video.frame` Event

- **Type**: `"pcmux.video.frame"`
- **Fields**:
  - **`mime`**: String indicating the MIME type of the image (e.g., `"image/png"`).
  - **`data`**: Base64-encoded image data.

**Message Structure:**

```json
{
  "type": "pcmux.video.frame",
  "mime": "image/png",
  "data": "<base64_encoded_image_data>"
}
```

#### `pcmux.text.chunk` Event

- **Type**: `"pcmux.text.chunk"`
- **Fields**:
  - **`speaker`**: String uniquely identifying the speaker of this text segment
  - **`text`**: Text from the speaker, typically transcribed from the audio

**Message Structure:**

```json
{
  "type": "pcmux.text.chunk",
  "speaker": "SPEAKER_01",
  "text": "Spoken or written text"
}
```

## Media Buffer Handling

### Receiving and Playing Audio Data

The client listens for messages of type `"pcmux.audio.delta"`, extracts the base64-encoded audio data from the `"delta"` field, decodes it back to raw PCM bytes, and handles the audio.

**Client-Side Process:**

1. **Receive Message**: The client receives a JSON message from the server.
2. **Parse JSON**: Extract the `"delta"` field from the message.
3. **Decode Base64**: Decode the base64 string to obtain raw PCM data.
4. **Handle Audio**: Process the PCM audio data or play it (e.g., using `pyaudio`), considering threading or asynchronous handling carefully.

**Client-Side Code Snippet (Python):**

```python
def on_message(ws, message):
    event = json.loads(message)
    if event.get("type") == "pcmux.audio.delta":
        audio_base64 = event.get("delta", "")
        if audio_base64:
            audio_data = base64.b64decode(audio_base64)
            stream.write(audio_data)
```

### Receiving and Processing Video Frame Snapshots

The client listens for messages of type `"pcmux.video.frame"`, extracts the base64-encoded image data from the `"data"` field, decodes it back to image bytes, and handles the image processing.

**Client-Side Process:**

1. **Receive Message**: The client receives a JSON message from the server.
2. **Parse JSON**: Extract the `"data"` field from the message.
3. **Decode Base64**: Decode the base64 string to obtain raw image bytes.
4. **Handle Image**: Process the image data (e.g., detect changes).

**Client-Side Code Snippet (Python):**

```python
from PIL import Image
import io

def on_message(ws, message):
    event = json.loads(message)
    if event.get("type") == "pcmux.video.frame":
        image_base64 = event.get("data", "")
        if image_base64:
            image_data = base64.b64decode(image_base64)
            image = Image.open(io.BytesIO(image_data))
            image.show()  # Or handle the image as needed
```

## Extensibility

While PCMux currently supports audio and video streaming, it is designed to be extensible. Developers can define additional event types to accommodate other media types or control messages as needed for their specific applications.

## Conclusion

PCMux provides a straightforward and efficient protocol for real-time media streaming using JSON over WebSockets or STDIO. By supporting both audio and video data types with base64 encoding, it ensures compatibility and ease of integration with various applications and services.