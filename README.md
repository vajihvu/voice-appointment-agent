# AI Voice Appointment Agent

A real-time AI Voice Appointment Agent built with FastAPI, WebSockets, Deepgram STT, LLM Tool Calling, and SQLite. Features a direct browser-based Web Audio transport (16 kHz PCM16 mono) with live microphone capture, real-time audio playback, client-side barge-in, multilingual conversation flows (English, Hindi, Kannada), transactional appointment booking, and in-database confirmation notifications.

---

## Project Status
- **Phase 2.5: Complete** (Browser-based Web Audio transport, audio resampling pipeline, transactional appointment booking, and in-database notifications are implemented and passing test suite).
- **Phase 3: Not Started** (Formal performance evaluation benchmarks and multi-call stress testing have not been started; any performance numbers listed in documentation are architectural targets or estimates only).

---

## Architecture & Transports

- **Browser Voice Transport**: Direct Web Audio API & AudioWorklet interface (`/ws/call`) streaming uncompressed 16 kHz PCM16 frames in full duplex. Free, developer-accessible, and requires no telecom carrier accounts or public reverse tunnels.
- **Legacy Telephony**: The historical Plivo Voice API implementation is permanently preserved in git history at tag `phase-2`.
- **Telephony Adapter Design**: An architectural blueprint for attaching external SIP gateways or PSTN carriers is documented in [docs/INTEGRATION_GUIDE.md](docs/INTEGRATION_GUIDE.md).

---

## Security & Repository Hygiene

To safeguard sensitive credentials (API tokens, private keys, and database binaries):
1. **Localhost Binding by Default**: Server binds strictly to `127.0.0.1`.
2. **WebSocket Origin & Token Checks**: `/ws/call` validates Origin headers against `ALLOWED_ORIGINS` and supports an optional shared `CALL_TOKEN`.
3. **Zero Secrets in Code**: All environment variables and credentials load from `.env` via `app/core/config.py`.
4. **Pre-Commit Secrets Hook**:
   - Automated pre-commit hook in `scripts/check_secrets.py` blocks commits containing:
     - `.env` files (or `.env.*`, except `.env.example`)
     - Database files (`*.db`, `*.sqlite`)
     - Hardcoded API credentials (OpenAI `sk-...`, Deepgram `dg-...`, Bearer tokens).
5. **Multi-layer Secret Scanning (`detect-secrets`)**:
   - Integrates Yelp's `detect-secrets` with `.secrets.baseline` to catch high-entropy strings and credentials across git history.
6. **Installing the Pre-Commit Hook**:
   ```bash
   # On macOS/Linux:
   chmod +x scripts/install_hooks.sh
   ./scripts/install_hooks.sh

   # On Windows / Cross-platform:
   python scripts/install_hooks.py
   ```
7. **PII and Secret Masking in Logs**:
   - `app/core/logging.py` includes `PIIMaskingFormatter` which dynamically scrubs phone numbers (`+9198*****210`) and authorization tokens.

---

## Quickstart

### 1. Requirements
- Python 3.11+
- Virtual environment (`venv`)

### 2. Installation
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

### 3. Configuration
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

### 4. Running the Server & Voice Studio
```bash
python run.py
```
Open your browser and navigate to:
```
http://127.0.0.1:8000
```
Click **Start Call** to test live two-way microphone audio streaming and instant barge-in.

### 5. Running the Offline Simulator
```bash
python simulator/call_simulator.py --interactive
```

### 6. Running Tests & Linters
```bash
# Run unit & integration tests
pytest -v

# Run code linter
ruff check .
```
