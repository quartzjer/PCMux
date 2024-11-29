# PCMux - WebSocket-Based Real-Time Audio Streaming Protocol

## Overview

This protocol defines a minimal structure for real-time audio streaming over WebSocket connections using JSON messages containing base64-encoded PCM audio data. It facilitates the transmission of audio data from a server to a client in real-time, suitable for applications like live audio feeds, voice assistants, and streaming services.

It is entirely derivative of and based on the [OpenAI Realtime API](https://platform.openai.com/docs/guides/realtime). This is just a minimal subset to support custom audio streaming applications that want to maximize compatibility with the Realtime API.

## WebSocket Connection

All messages are sent over a standard WebSocket connection.  This specification only defines one event type to carry audio over that socket, other event types can be used for application specific needs.

## Audio Encoding Specifications

- **Format**: PCM (Pulse-Code Modulation)
- **Sample Format**: 16-bit signed integers (`paInt16`)
- **Channels**: Mono (1 channel)
- **Sampling Rate**: 24,000 Hz
- **Chunk Size**: 1,024 frames per buffer

PCM audio data is base64-encoded before being embedded in JSON messages.

## Audio Message Format

### Event Definitions

- **`type`**: String indicating the event type (e.g., `"pcm.audio.delta"`).
- **`...`**: All other fields are specific to the event type.

### `pcmux.audio.delta` Event

- **Type**: `"pcmux.audio.delta"`
- **Field**: `"delta"` contains the base64-encoded PCM audio data.

**Message Structure:**

```json
{
  "type": "pcmux.audio.delta",
  "delta": "<base64_encoded_pcm_data>"
}
```

**Example:**

```json
{
  "type": "pcmux.audio.delta",
  "delta": "UklGRiQAAABXQVZFZm10IBAAAAABAAEAESsAACJWAAACABAAZGF0YQAAAAA="
}
```

## Audio Buffer Handling

### Receiving and Playing Audio Data

The client listens for messages of type `"pcmux.audio.delta"`, extracts the base64-encoded audio data from the `"delta"` field, decodes it back to raw PCM bytes, and handles the audio.

**Client-Side Process:**

1. **Receive Message**: The client receives a JSON message from the server.
2. **Parse JSON**: Extract the `"delta"` field from the message.
3. **Decode Base64**: Decode the base64 string to obtain raw PCM data.
4. **Handle Audio**: Process the PCM audio data or play it (e.g., using `pyaudio`), consider threading or async handling carefully.

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

## PCM and Base64 Encoding Specifics

### PCM Audio Data

- **Bit Depth**: 16 bits per sample
- **Byte Order**: Little-endian
- **Data Rate**: For mono audio at 24 kHz, the data rate is 48,000 bytes per second (24,000 samples/sec × 2 bytes/sample).

### Base64 Encoding

- Base64 encoding converts binary PCM data into ASCII strings suitable for transmission as JSON.

**Encoding Example:**

```python
import base64
audio_base64 = base64.b64encode(pcm_data).decode('utf-8')
```

**Decoding Example:**

```python
import base64
pcm_data = base64.b64decode(audio_base64)
```
