# Integration & Deployment Guide

This guide explains how to run the AI Voice Appointment Agent locally using the browser audio studio, and details how a commercial telephony or SIP provider adapter can be plugged into the `VoiceTransport` interface.

---

## 1. Browser Voice Studio (Local Ingress)

The primary transport for development, testing, and portfolio demonstrations is the built-in Browser Web Audio transport:
- **Server Address**: `http://127.0.0.1:8000`
- **Voice Studio URL**: `http://127.0.0.1:8000/call` (or `/`)
- **WebSocket Endpoint**: `ws://127.0.0.1:8000/ws/call`

### Running the Voice Studio
1. Start the FastAPI server:
   ```bash
   python run.py
   ```
2. Open `http://127.0.0.1:8000` in Google Chrome, Microsoft Edge, or Mozilla Firefox.
3. Click **Start Call** and grant microphone permissions.
4. Speak into your microphone. The client captures 16 kHz mono audio via an `AudioWorklet`, streams it to the server, and plays back agent responses with instant barge-in support.

---

## 2. Telephony & SIP Adapter Architecture

> [!IMPORTANT]
> ### ⚠️ DESIGN ONLY / UNTESTED ARCHITECTURE
> The telephony adapter blueprint documented in this section illustrates the architectural design for plugging an external PSTN/SIP gateway or cloud telephony provider (such as Twilio, Telnyx, or a FreeSWITCH/Asterisk SIP trunk) into the `VoiceTransport` interface.
> **This adapter is an untested architectural design and is not active in the default test suite.**

### The `VoiceTransport` Contract
The core conversation engine (`CallSession`) interacts exclusively with `app.transport.base.VoiceTransport`:
```python
class VoiceTransport(ABC):
    async def start(self) -> None: ...
    async def receive_audio(self) -> AsyncGenerator[bytes, None]: ...
    async def send_audio(self, pcm_bytes: bytes) -> None: ...
    async def clear_audio(self) -> None: ...
    async def send_event(self, event_type: str, data: dict) -> None: ...
    async def close(self) -> None: ...
```

### Telephony Adapter Blueprint (Conceptual Design)
To connect a cloud telephony provider or SIP gateway, an adapter subclasses `VoiceTransport` and implements three tasks:

1. **Protocol Ingress & Signaling**:
   - Accepts the provider's inbound audio stream (e.g., Twilio Media Streams, Telnyx TeXML Streams, or SIP RTP over UDP/WebSocket).
2. **Audio Resampling & Transcoding**:
   - Standard PSTN telephony typically operates at 8,000 Hz mono G.711 $\mu$-law or A-law.
   - The adapter must decode incoming 8kHz $\mu$-law frames to 16-bit linear PCM and resample from 8,000 Hz to 16,000 Hz before yielding to `receive_audio()`.
   - Conversely, outbound 16 kHz PCM from `send_audio()` must be downsampled to 8,000 Hz and encoded to $\mu$-law before transmission over the carrier socket.
3. **Barge-in Mapping**:
   - When the agent triggers `clear_audio()`, the adapter maps this to the provider-specific clear packet (e.g., Twilio `{"event": "clear", "streamSid": "..."}`).

#### Reference Skeleton Code:
```python
# DESIGN ONLY - ARCHITECTURAL BLUEPRINT (UNTESTED)
from app.transport.base import VoiceTransport

class TelephonyProviderAdapter(VoiceTransport):
    """Untested conceptual adapter bridging a telephony WebSocket to VoiceTransport."""

    def __init__(self, carrier_ws, stream_id: str):
        self.carrier_ws = carrier_ws
        self.stream_id = stream_id

    async def start(self) -> None:
        pass

    async def receive_audio(self):
        # 1. Read carrier frames
        # 2. Base64 decode payload
        # 3. Transcode 8kHz mu-law -> 16kHz PCM16
        # 4. yield 16kHz PCM16 bytes
        pass

    async def send_audio(self, pcm_bytes: bytes) -> None:
        # 1. Downsample 16kHz PCM16 -> 8kHz
        # 2. Encode to mu-law and base64
        # 3. Send carrier media packet (e.g. playAudio / media)
        pass

    async def clear_audio(self) -> None:
        # Send carrier-specific buffer flush packet
        pass

    async def send_event(self, event_type: str, data: dict) -> None:
        pass

    async def close(self) -> None:
        await self.carrier_ws.close()
```

---

## 3. Data Privacy & Retention Policy

1. **Local SQLite Persistence**: All appointment bookings, turn latencies, and confirmation notifications are persisted locally in `voice_agent.db`.
2. **PII Masking**: Caller phone numbers and sensitive credentials are automatically masked in standard application logs (`+9198*****210`).
3. **Automated Transcript Purging**: Call records older than `TRANSCRIPT_RETENTION_DAYS` (default 30 days) have their full transcript text sanitized to `[PURGED_BY_RETENTION_POLICY]` via `app.db.repository.purge_old_transcripts`.
