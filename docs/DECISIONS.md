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

### STT & TTS Provider Compatibility Matrix

| Provider & Component | Target Audio Format | Documentation URL | Paraphrased Claim | Verification Status |
| :--- | :--- | :--- | :--- | :--- |
| **Browser Web Audio Capture** | PCM16, 16 kHz, Mono | [W3C Web Audio API Spec](https://www.w3.org/TR/webaudio/) | AudioWorklet processes native input audio and linear interpolation downsamples to 16 kHz 16-bit signed integer frames. | **VERIFIED** |
| **Deepgram Live Streaming STT** | `linear16`, 16 kHz, Mono | [Deepgram Audio Formats](https://developers.deepgram.com/docs/streaming-audio-formats) | Deepgram's live WebSocket endpoint ingests raw uncompressed PCM audio with query parameters `encoding=linear16&sample_rate=16000&channels=1`. | **VERIFIED** |
| **OpenAI Whisper STT** | Multipart Audio File | [OpenAI Audio API Reference](https://platform.openai.com/docs/api-reference/audio/createTranscription) | Whisper API (`/v1/audio/transcriptions`) is a file-upload REST endpoint (mp3/wav) for batch transcription, not a real-time bidirectional streaming WebSocket. | **UNVERIFIED (Incompatible with live streaming)** |
| **Deepgram Aura Streaming TTS** | `linear16`, 16 kHz, Mono | [Deepgram Aura TTS Streaming](https://developers.deepgram.com/docs/tts-streaming) | Aura WebSocket and REST streaming endpoints output uncompressed 16 kHz PCM using `encoding=linear16&sample_rate=16000`. | **VERIFIED** |
| **Cartesia Sonic Streaming TTS** | `pcm_16000`, 16 kHz, Mono | [Cartesia Sonic WebSocket API](https://docs.cartesia.ai/build-with-sonic/stream-audio) | Cartesia's WebSocket streaming API delivers raw 16 kHz 16-bit linear PCM audio chunks when requested with format `pcm_16000`. | **VERIFIED** |
| **ElevenLabs Streaming TTS** | `pcm_16000`, 16 kHz, Mono | [ElevenLabs Text-to-Speech Stream](https://elevenlabs.io/docs/api-reference/text-to-speech-stream) | ElevenLabs streaming API delivers raw 16 kHz 16-bit mono PCM chunks when query parameter `output_format=pcm_16000` is specified. | **VERIFIED** |
| **Proprietary SIP / WebRTC Codecs** | G.722, Opus, AMR-WB | N/A | Untested; requires external gateway and RTP transcoding pipeline to bridge to 16 kHz linear PCM. | **UNVERIFIED** |

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
