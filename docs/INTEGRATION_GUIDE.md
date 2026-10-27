# Integration & Deployment Guide

This guide explains how to set up, expose, and integrate the AI Voice Appointment Agent with Plivo, including local tunneling, regulatory constraints, and data privacy policies.

---

## 1. Local Telephony Ingress (Tunneling)

Because Plivo needs to reach your server via public HTTPS webhooks and WebSockets (`wss://`), you must expose your local development server to the internet using **ngrok** or **Cloudflare Tunnel**.

### Option A: Using ngrok
```bash
# Expose local port 8000
ngrok http 8000
```
- Copy the Forwarding URL (e.g. `https://abc1234.ngrok-free.app`).
- Set `BASE_URL=https://abc1234.ngrok-free.app` in your `.env`.

### Option B: Using Cloudflare Tunnel (Free & No session timeout)
```bash
# Install cloudflared (via brew, scoop, or direct download)
cloudflared tunnel --url http://localhost:8000
```
- Copy the generated `https://*.trycloudflare.com` URL to `BASE_URL` in `.env`.

---

## 2. Plivo Console Configuration

1. Log into your [Plivo Console](https://console.plivo.com/).
2. Navigate to **Voice > Applications** and click **Add New Application**:
   - **Application Name**: `Dental-AI-Voice-Agent`
   - **Answer URL**: `https://<YOUR_TUNNEL_URL>/webhook/plivo/answer` (Method: `POST`)
   - **Fallback URL**: `https://<YOUR_TUNNEL_URL>/webhook/plivo/fallback` (Method: `POST`)
   - **Hangup URL**: `https://<YOUR_TUNNEL_URL>/webhook/plivo/hangup` (Method: `POST`)
3. Navigate to **Phone Numbers**, select your active Plivo number, and attach the application you just created.

### ⚠️ Critical Note: Plivo Trial Account Limits
- On a Plivo Trial Account, **outbound calls, SMS, and human-handoff forwarding can ONLY connect to verified sandbox numbers**.
- **Action Required**:
  1. Go to **Phone Numbers > Sandbox Numbers** in Plivo Console.
  2. Add and verify your personal phone number and the clinic receptionist's number (`HUMAN_HANDOFF_NUMBER`).
  3. Attempting to transfer calls or send SMS to unverified numbers on trial accounts will return an HTTP 400 error.

---

## 3. Telephony Regulatory Compliance (India +91 / TRAI)

If deploying for clinics in India using Indian phone numbers (+91):
- **DLT (Distributed Ledger Technology)**: TRAI mandates registration of Entity ID, Sender Header (e.g., `BRTSML`), and SMS Content Templates.
- Our system supports configurable DLT headers in `config/business_config.yaml`:
  ```yaml
  sms:
    enabled: true
    sender_id: "BRTSML"
    dlt_entity_id: "100123456789"
    dlt_template_id: "12071618293040"
  ```
- If testing in sandbox mode without DLT, SMS can be toggled off (`ENABLE_SMS_CONFIRMATION=false`), or simulated using the local test harness.

---

## 4. Privacy & Data Protection Policy

1. **PII Masking**:
   - Caller phone numbers are masked in all standard application logs and dashboard reports (e.g., `+91 98*** **210`).
   - Plaintext phone numbers are stored strictly within the ACID database for legitimate appointment reminder operations.
2. **Transcript Retention Policy**:
   - Transcripts are retained for a configurable retention window (default: `TRANSCRIPT_RETENTION_DAYS=30`).
   - The automated cleanup task `purge_old_transcripts(retention_days)` scrubs dialogue transcripts older than the window, replacing them with `[PURGED_BY_RETENTION_POLICY]`.
3. **Secret Storage**:
   - API keys and telephony auth tokens must never be committed to Git. All secrets are read from the `.env` file using Pydantic Settings.
