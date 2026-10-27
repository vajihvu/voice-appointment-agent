# AI Voice Appointment Agent

An inbound telephony AI voice agent answering calls on a Plivo phone number, conducting real-time bidirectional audio streaming over WebSockets, executing multilingual conversational flows with LLM tool calling (dental clinic appointment booking, cancellation, and human receptionist handoff), and persisting call metrics and latencies into SQLite.

---

## Security & Repository Hygiene

To safeguard sensitive credentials (API tokens, private telephony auth IDs, and database binaries):
1. **Zero Secrets in Code**: All environment variables and secrets are loaded from `.env` via `app/core/config.py`.
2. **Pre-Commit Secrets Hook**:
   - The repository includes an automated pre-commit secret detector in `scripts/check_secrets.py` (with bash wrapper `scripts/check_secrets.sh`).
   - It intercepts staged changes and automatically **blocks commits** containing:
     - `.env` files (or `.env.*`, except `.env.example`)
     - Database files (`*.db`, `*.sqlite`)
     - Ngrok configuration files
     - Hardcoded API keys (e.g. OpenAI `sk-...`, Deepgram `dg-...`, Plivo Auth Tokens, Bearer tokens).
3. **Installing the Pre-Commit Hook**:
   ```bash
   # On macOS/Linux:
   cp scripts/check_secrets.sh .git/hooks/pre-commit
   chmod +x .git/hooks/pre-commit

   # On Windows:
   cp scripts/check_secrets.sh .git/hooks/pre-commit
   # Or run check directly:
   python scripts/check_secrets.py
   ```
4. **PII and Secret Masking in Logs**:
   - `app/core/logging.py` includes `PIIMaskingFormatter` which dynamically scrubs caller phone numbers (`+9198*****210`) as well as any authorization tokens, passwords, or API keys from terminal and application logs.

---

## Quickstart

### 1. Requirements
- Python 3.11+
- Virtual environment (`venv`)

### 2. Installation
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -e .
```

### 3. Configuration
Copy `.env.example` to `.env` and fill in your credentials:
```bash
cp .env.example .env
```

### 4. Running the Server
```bash
python run.py
```

### 5. Running the Offline Simulator
```bash
python simulator/call_simulator.py --interactive
```

### 6. Running Tests
```bash
pytest -v
```
