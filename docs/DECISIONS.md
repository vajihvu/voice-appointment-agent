# Architectural & Engineering Decisions (ADR)

## Decision 1: Telephony Provider - Plivo Voice API & Audio Streaming

- **Context**: Inbound phone calls require bidirectional real-time audio streaming and webhook handling to integrate with conversational AI pipelines.
- **Documentation Verification & Claim Citations**:
  Every URL below supports a specific verified protocol specification:

  | Specific Claim / Feature | Verified Plivo Documentation URL | Verification Status |
  | :--- | :--- | :--- |
  | **`<Stream>` XML element & child text**: Encloses the public WebSocket URL (`wss://...`). | [https://www.plivo.com/docs/voice/xml/stream/](https://www.plivo.com/docs/voice/xml/stream/) | **VERIFIED** |
  | **`<Stream>` attribute `bidirectional`**: Set to `"true"` to enable simultaneous inbound and outbound audio on the WebSocket connection. | [https://www.plivo.com/docs/voice/xml/stream/](https://www.plivo.com/docs/voice/xml/stream/) | **VERIFIED** |
  | **`<Stream>` attribute `keepCallAlive`**: Set to `"true"` to prevent the call from disconnecting when child elements finish or when the stream initiates. | [https://www.plivo.com/docs/voice/xml/stream/](https://www.plivo.com/docs/voice/xml/stream/) | **VERIFIED** |
  | **`<Stream>` attribute `contentType`**: Specifies audio encoding format `audio/x-mulaw;rate=8000` (8000Hz mono G.711 $\mu$-law). | [https://www.plivo.com/docs/voice/xml/stream/](https://www.plivo.com/docs/voice/xml/stream/) | **VERIFIED** |
  | **`<Stream>` attributes `streamTimeout`, `statusCallbackUrl`, `statusCallbackMethod`**: Stream lifecycle settings and webhook hooks for connection notifications. | [https://www.plivo.com/docs/voice/xml/stream/](https://www.plivo.com/docs/voice/xml/stream/) | **VERIFIED** |
  | **WebSocket Inbound `event: "start"`**: Carries metadata `streamId`, `callId`, and `mediaFormat` (`encoding: "audio/x-mulaw"`, `sampleRate: 8000`). | [https://www.plivo.com/docs/voice/guides/audio-streaming/](https://www.plivo.com/docs/voice/guides/audio-streaming/) | **VERIFIED** |
  | **WebSocket Inbound `event: "media"`**: Audio delivered in 20ms chunks (160 bytes) base64-encoded in `media.payload` with sequence `chunk` and `timestamp`. | [https://www.plivo.com/docs/voice/guides/audio-streaming/](https://www.plivo.com/docs/voice/guides/audio-streaming/) | **VERIFIED** |
  | **WebSocket Inbound `event: "stop"`**: Sent by Plivo when the call or stream terminates, carrying `streamId`. | [https://www.plivo.com/docs/voice/guides/audio-streaming/](https://www.plivo.com/docs/voice/guides/audio-streaming/) | **VERIFIED** |
  | **WebSocket Outbound `event: "playAudio"`**: Packet containing synthesized audio: `{"event": "playAudio", "media": {"contentType": "audio/x-mulaw", "sampleRate": 8000, "payload": "<base64>"}}`. | [https://www.plivo.com/docs/voice/guides/audio-streaming/](https://www.plivo.com/docs/voice/guides/audio-streaming/) | **VERIFIED** |
  | **WebSocket Outbound `event: "clearAudio"`**: Instant barge-in audio clearing: `{"event": "clearAudio", "streamId": "<streamId>"}`. | [https://www.plivo.com/docs/voice/guides/audio-streaming/](https://www.plivo.com/docs/voice/guides/audio-streaming/) | **VERIFIED** |
  | **WebSocket Outbound `mark` / `checkpoint` events**: Outbound marker packets for client-side playback tracking (like Twilio `mark`). Not documented in official Plivo audio streaming documentation. | N/A | **UNVERIFIED** (We do not rely on marker events; audio duration tracking is handled server-side). |
  | **WebSocket Inbound `event: "dtmf"`**: Structure of DTMF touch-tone events (`{"event": "dtmf", ...}`) during audio streams. Not officially defined in the main streaming guide table. | [https://www.plivo.com/docs/voice/guides/audio-streaming/](https://www.plivo.com/docs/voice/guides/audio-streaming/) | **UNVERIFIED** (We do not rely on DTMF events; interaction is voice-driven via STT). |
  | **Webhook Signature Validation (V3)**: Voice webhooks include headers `X-Plivo-Signature-V3`, `X-Plivo-Signature-Ma-V3`, and `X-Plivo-Signature-V3-Nonce`. Validation is computed using HMAC-SHA256 with key = `PLIVO_AUTH_TOKEN` over `URL + "." + nonce`, base64 encoded. | [https://www.plivo.com/docs/voice/guides/signature-validation/](https://www.plivo.com/docs/voice/guides/signature-validation/) | **VERIFIED** |
  | **Plivo Trial Destination Limitations**: Outbound SMS, call forwarding, and human-handoff targets fail with HTTP 400 unless pre-verified as Sandbox Numbers in the Plivo Console. | [https://www.plivo.com/docs/voice/guides/call-forwarding/](https://www.plivo.com/docs/voice/guides/call-forwarding/) | **VERIFIED** |

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
