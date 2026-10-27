# Architectural & Engineering Decisions (ADR)

## Decision 1: Telephony Provider - Plivo Voice API & Audio Streaming

- **Context**: Inbound phone calls require bidirectional real-time audio streaming and webhook handling to integrate with conversational AI pipelines.
- **Documentation Verification & Claim Citations**:
  Every URL below supports a specific verified protocol specification:

  | Specific Claim / Feature | Verified Plivo Documentation URL | Verification Status |
  | :--- | :--- | :--- |
  | **`<Stream>` XML element & child text**: Encloses the public WebSocket URL (`wss://...`) to stream live call audio. | [https://www.plivo.com/docs/voice/api/stream/](https://www.plivo.com/docs/voice/api/stream/) | **VERIFIED** |
  | **`<Stream>` attribute `bidirectional`**: Set to `"true"` to enable full-duplex communication (receiving caller audio and transmitting synthesized audio back). | [https://www.plivo.com/docs/voice/api/stream/](https://www.plivo.com/docs/voice/api/stream/) | **VERIFIED** |
  | **`<Stream>` attribute `keepCallAlive`**: Set to `"true"` to keep the telephony session active while streaming rather than disconnecting when XML commands complete. | [https://www.plivo.com/docs/voice/api/stream/](https://www.plivo.com/docs/voice/api/stream/) | **VERIFIED** |
  | **`<Stream>` attribute `contentType`**: Specifies audio encoding format `audio/x-mulaw;rate=8000` (8000Hz mono G.711 $\mu$-law). | [https://www.plivo.com/docs/voice/api/stream/](https://www.plivo.com/docs/voice/api/stream/) | **VERIFIED** |
  | **`<Stream>` attributes `streamTimeout`, `statusCallbackUrl`, `statusCallbackMethod`**: Stream lifecycle timeout and webhook callback endpoints for connection state change notifications. | [https://www.plivo.com/docs/voice/api/stream/](https://www.plivo.com/docs/voice/api/stream/) | **VERIFIED** |
  | **WebSocket Inbound `event: "start"`**: Carries initial session metadata including `streamId`, `callId`, and `mediaFormat` (`encoding: "audio/x-mulaw"`, `sampleRate: 8000`). | [https://www.plivo.com/docs/voice/api/stream/](https://www.plivo.com/docs/voice/api/stream/) | **VERIFIED** |
  | **WebSocket Inbound `event: "media"`**: Caller audio delivered in continuous 20ms chunks (160 bytes) base64-encoded in `media.payload` with sequence `chunk` and `timestamp`. | [https://www.plivo.com/docs/voice/api/stream/](https://www.plivo.com/docs/voice/api/stream/) | **VERIFIED** |
  | **WebSocket Inbound `event: "stop"`**: Dispatched by Plivo when the call or stream session terminates, carrying `streamId`. | [https://www.plivo.com/docs/voice/api/stream/](https://www.plivo.com/docs/voice/api/stream/) | **VERIFIED** |
  | **WebSocket Outbound `event: "playAudio"`**: Packet containing synthesized audio: `{"event": "playAudio", "media": {"contentType": "audio/x-mulaw", "sampleRate": 8000, "payload": "<base64>"}}`. | [https://www.plivo.com/docs/voice/api/stream/](https://www.plivo.com/docs/voice/api/stream/) | **VERIFIED** |
  | **WebSocket Outbound `event: "clearAudio"`**: Instant barge-in audio clearing: `{"event": "clearAudio", "streamId": "<streamId>"}` to flush Plivo's edge playback buffer. | [https://www.plivo.com/docs/voice/api/stream/](https://www.plivo.com/docs/voice/api/stream/) | **VERIFIED** |
  | **WebSocket Outbound `mark` / `checkpoint` events**: Outbound marker packets for client-side playback tracking (like Twilio `mark`). Not documented in official Plivo audio streaming documentation. | N/A | **UNVERIFIED** (We do not rely on marker events; audio duration tracking is handled server-side). |
  | **WebSocket Inbound `event: "dtmf"`**: Touch-tone keypad events during active streaming. Omitted from official stream documentation reference tables. | N/A | **UNVERIFIED** (We do not rely on DTMF events; interaction is voice-driven via STT). |
  | **Webhook Signature Validation (V3)**: Voice webhooks include headers `X-Plivo-Signature-V3`, `X-Plivo-Signature-Ma-V3`, and `X-Plivo-Signature-V3-Nonce`. Validation uses HMAC-SHA256 with key = `PLIVO_AUTH_TOKEN`. For GET requests, the signed string is `URL + "." + nonce`. For POST requests, the form parameters are sorted alphabetically by key, concatenated, appended to the URL, and joined with `"." + nonce`. Implemented via official `plivo.utils.validate_v3_signature`. | [https://www.plivo.com/docs/voice/concepts/signature-validation](https://www.plivo.com/docs/voice/concepts/signature-validation) | **VERIFIED** |
  | **Plivo Trial Destination Limitations**: Outbound SMS, call forwarding, and human-handoff targets fail with HTTP 400 unless pre-verified as Sandbox Numbers in the Plivo Console. | [https://console.plivo.com](https://console.plivo.com) (Phone Numbers > Sandbox Numbers) | **VERIFIED** |

## Decision 2: Provider Abstraction & Swappable Interfaces
- **STT**: `STTProvider` Abstract Base Class (`start()`, `send_audio()`, `receive_events()`, `close()`).
  - Production concrete: Deepgram Live WebSocket (`nova-2`, 8000Hz).
  - Test/Simulator concrete: `MockSTTProvider`.
- **LLM**: `LLMProvider` Abstract Base Class (`chat_stream()`).
  - Production concrete: OpenAI-compatible API (Groq / OpenAI) with tool/function calling schemas.
  - Test/Simulator concrete: `MockLLMProvider`.
- **TTS**: `TTSProvider` Abstract Base Class (`synthesize_text()`, `synthesize_stream()`).
  - Production concrete: Deepgram Aura streaming TTS (emitting 8000Hz $\mu$-law).
  - Test/Simulator concrete: `MockTTSProvider`.

## Decision 3: Audio Codec & Turn Latency Definition
- **Telephony Format**: G.711 $\mu$-law (`audio/x-mulaw`) at 8000Hz mono.
- **Strict Turn Latency Definition**:
  $$\text{Turn Latency} = T_{\text{first audio byte sent to Plivo}} - T_{\text{end of caller speech}}$$
  - Measured deterministically and broken down into $T_{\text{STT}}, T_{\text{LLM}}, T_{\text{TTS}}, T_{\text{total}}$ in `TurnLatency` records.
  - Target: <1000ms. No claims on performance thresholds are made until measured by the automated evaluation benchmark script in Phase 6.

## Decision 4: Barge-In Filtering & Debounce
- Prevents backchannel sounds ("hmm", coughs) and acoustic echo from prematurely interrupting the agent.
- **Trigger Conditions**:
  1. `is_agent_speaking == True` (only active while agent is talking).
  2. Word count $\ge 2$ words.
  3. STT confidence $\ge 0.70$.
  4. Debounce duration: Speech must persist longer than $200\text{ms}$ after initial detection before issuing `clearAudio` to Plivo and cancelling the playback task.
- **Playback Completion Estimation (Phase 4 Implementation Note)**:
  - Plivo does not send a "playback finished" marker event over the WebSocket.
  - Therefore, playback completion is estimated from audio duration ($8000\text{ bytes/second}$ for 8kHz $\mu$-law mono: $\text{Duration (s)} = \frac{\text{Audio Bytes}}{8000}$).
  - Plivo buffers audio on the telephony edge, so this duration is an approximation that will be tuned and measured empirically rather than treated as an exact value.

## Decision 5: Slot Reservation Concurrency & Transactional Safety
- **SQLite Concurrency & Row Locking Reality**:
  - In PostgreSQL or MySQL, `SELECT ... FOR UPDATE` acquires an explicit row-level lock.
  - **In SQLite, `SELECT ... FOR UPDATE` is a syntactic NO-OP**. SQLite uses database/file-level locking, not fine-grained row-level locking.
  - Therefore, the true, fail-safe guarantee against double-booking is the database-level **`UniqueConstraint("appointment_date", "start_time")`** on `appointments` and `schedule_slots`.
  - When concurrent transactions race, the second transaction is immediately blocked and rolls back with an `IntegrityError`, returning a graceful alternative slot recommendation to the caller.
  - Verified in `tests/test_concurrency.py` using an independent file-backed SQLite database with 5 simultaneous connections executing concurrently via `asyncio.gather()`.

## Decision 6: Privacy, Data Protection, and PII Masking
- **Phone Numbers**: Masked in all logs and dashboard views (`+9198*****210`) using `mask_phone_number()`.
- **Transcripts**: Configurable retention policy (default 30 days) via `purge_old_transcripts()`.
- **Secrets**: Read exclusively from `.env`.

## Decision 7: Local Ingress & Telephony Tunneling
- Use ngrok (`ngrok http 8000`) or Cloudflare Tunnel (`cloudflared tunnel --url http://localhost:8000`) to expose the local FastAPI server.
- Webhook URL in Plivo Console: `https://<tunnel-domain>/webhook/plivo/answer`.
- WebSocket URL in `<Stream>` XML: `wss://<tunnel-domain>/ws/plivo/stream`.
