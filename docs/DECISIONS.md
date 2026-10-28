# Architectural & Engineering Decisions (ADR)

## Decision 1: Architectural Pivot - Replacing Plivo with Browser Web Audio Transport

### Context & Problem
In the initial project architecture (preserved in git history under git tag `phase-2`), inbound telephony was built on Plivo's Voice API, XML Stream webhooks, and G.711 $\mu$-law WebSockets. However, Plivo updated its onboarding policies to gate number acquisition and trial voice features behind corporate business registration, blocking individual student and independent developers.

### Decision
1. **Remove Plivo from active code**: Drop Plivo SDK dependency, signature validators, XML endpoints, and 8kHz $\mu$-law transcoding.
2. **Preserve Legacy Implementation in Git**: Git tag `phase-2` permanently preserves the complete working Plivo implementation in version control history.
3. **Introduce `VoiceTransport` Interface**: Abstract audio I/O, barge-in signals, and connection lifecycles behind `VoiceTransport`.
4. **Implement Browser Web Audio Transport (`BrowserVoiceTransport`)**:
   - Zero financial barrier and zero carrier account gating.
   - Runs locally on `http://127.0.0.1:8000`.
   - Captures microphone audio using browser `navigator.mediaDevices.getUserMedia` with echo cancellation and noise suppression.
   - Encodes and buffers audio via `AudioWorklet` as raw 16 kHz PCM16 frames over WebSocket `/ws/call`.
   - Plays agent audio smoothly with the Web Audio API and provides instant barge-in clearing.

---

## Decision 2: Transport Abstraction (`VoiceTransport`)

The conversational session state machine (`CallSession`) is decoupled from underlying network protocols:

```
[Browser Client / Mic]  <--- WebSocket ---> [BrowserVoiceTransport]
                                                      |
                                                      v
                                              [VoiceTransport ABC]
                                                      |
                                                      v
                                                [CallSession]
                                          (STT -> LLM -> Tools -> TTS)
```

- **`VoiceTransport` ABC**:
  - `start() -> None`: Initializes transport lifecycle.
  - `receive_audio() -> AsyncGenerator[bytes, None]`: Streams raw PCM16 16kHz mono frames.
  - `send_audio(pcm_bytes: bytes) -> None`: Transmits synthesized PCM16 16kHz audio.
  - `clear_audio() -> None`: Emits barge-in interrupt (`{"type": "clear"}`) to flush listener buffers.
  - `send_event(event_type: str, data: dict) -> None`: Dispatches live transcripts and call state updates.
  - `close() -> None`: Cleanly terminates the transport session.

---

## Decision 3: Single Audio Format (PCM16 16 kHz Mono) & Provider Codec Audit

To maximize audio quality and eliminate transcoding latency and quantization noise, the system adopts **PCM16 (linear 16-bit signed integer, 16,000 Hz, mono)** end-to-end.

### Active STT & TTS Provider Compatibility Matrix

| Provider & Component | Target Audio Format | Full Documentation URL | Paraphrased Claim | Verification Status |
| :--- | :--- | :--- | :--- | :--- |
| **Deepgram Live Streaming STT** | `linear16`, 16 kHz, Mono | https://developers.deepgram.com/docs/streaming-audio-formats | Live WebSocket streaming accepts uncompressed 16-bit linear PCM frames with query parameters `encoding=linear16&sample_rate=16000&channels=1`. | **VERIFIED** |
| **Deepgram Aura Streaming TTS** | `linear16`, 16 kHz, Mono | https://developers.deepgram.com/docs/tts-streaming | Aura streaming endpoints return raw uncompressed 16 kHz 16-bit linear PCM frames when requested with `encoding=linear16&sample_rate=16000`. | **VERIFIED** |
| **Browser Web Audio Capture** | PCM16, 16 kHz, Mono | https://www.w3.org/TR/webaudio/ | Internal codebase design: AudioWorklet captures mic input and downsamples to 16 kHz PCM16 frames; verified by unit tests, but real-world browser behavior remains UNVERIFIED until manual live test. | **UNVERIFIED (Pending manual browser testing)** |

### Alternative Providers (Considered, Not Verified)
The following providers were considered during architecture planning but are not verified in active code:
- **OpenAI Whisper STT**: The OpenAI Whisper API (`/v1/audio/transcriptions`) is a file-upload REST endpoint designed for batch transcription, not a real-time bidirectional audio streaming WebSocket. Incompatible with low-latency live streaming.
- **Cartesia Sonic Streaming TTS**: Explored as a low-latency voice model. Format parameters and live streaming behavior have not been verified against current documentation.
- **ElevenLabs Streaming TTS**: Explored as an alternative voice option. Format parameters and streaming WebSocket behavior have not been verified against current documentation.

### Known Limitations
- **Linear Interpolation Resampling**: Both the client AudioWorklet and Python backend resamplers perform linear interpolation without an anti-aliasing low-pass filter. While computationally lightweight with sub-millisecond overhead, spectral aliasing is mathematically possible when downsampling from 44.1 kHz or 48 kHz to 16 kHz. Revisit with a windowed sinc or polyphase filter if live STT accuracy suffers.

---

## Decision 4: Turn Latency Definition

### Definition
$$\text{Turn Latency} = T_{\text{first agent audio byte sent over WebSocket}} - T_{\text{end of caller speech}}$$

- **Scope**: Measures server-side turn turnaround time:
  $$\text{Turn Latency} = T_{\text{STT processing}} + T_{\text{LLM first chunk}} + T_{\text{TTS first frame synthesis}}$$
- **Exclusions**: Explicitly excludes client-side hardware microphone buffering, browser Web Audio scheduling delay, and network round-trip transit.
- **Reporting**: Architectural design target: `<1000ms` (unmeasured target; formal empirical latency benchmarks have not been executed as Phase 3 is not started). Server turnaround will be recorded in `turn_latencies` database records.

---

## Decision 5: Instant Barge-In with Client-Side Buffer Flushing

- When the caller speaks while the agent is speaking:
  1. The server's barge-in evaluator checks speech criteria (word count $\ge 2$, confidence $\ge 0.70$, debounce $>200\text{ms}$).
  2. If satisfied, the server halts its TTS synthesis task immediately and sends `{"type": "clear"}` over the WebSocket.
  3. The browser client receives `{"type": "clear"}`, immediately stops all active `AudioBufferSourceNode` instances, and resets `nextPlaybackTime = audioContext.currentTime`.
  4. Audio playback halts instantly in the user's ears without residual buffer spillover.

---

## Decision 6: Notification System & Human Handoff Redesign

1. **Appointment Confirmations via `Notifier`**:
   - Replaced Plivo SMS with `Notifier` interface.
   - Default implementation: `DatabaseNotifier` writes confirmation records into the SQLite `notifications` table.
   - Displays confirmation details in the Streamlit management dashboard without external carrier fees or delivery failures.
2. **Human Handoff as Callback Request**:
   - `transfer_to_human` records a priority callback request with reason, customer contact details, and timestamp.
   - The agent informs the caller: *"I have registered your request. One of our clinic team members will follow up with you shortly."*
   - Eliminates complex telephony carrier bridging while accurately capturing user intent.

---

## Decision 7: Security & Network Surface

- **Default Binding**: Binds to `127.0.0.1` (localhost).
- **No Public Tunnels Required**: Does not require ngrok or Cloudflare Tunnel for development or evaluation.
- **WebSocket Security**:
  - Validates `Origin` header against `ALLOWED_ORIGINS` (rejecting unpermitted external sites).
  - Optional shared secret `CALL_TOKEN` validated via query parameter `?token=...` or headers. Fails closed with WebSocket close code `1008` (Policy Violation) if configured and invalid.
