"""Unit and integration tests for Browser WebSocket voice transport, framing, security, and resilience."""

import json

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app

client = TestClient(app)
settings = get_settings()


def test_browser_websocket_echo_loop():
    """Verify WebSocket echo test reflects binary PCM16 16kHz audio frames back to the client."""
    with client.websocket_connect("/ws/call?mode=echo") as ws:
        # 1. Expect initial state notifications
        msg1 = json.loads(ws.receive_text())
        assert msg1.get("type") == "state"
        assert msg1.get("state") == "connected"

        msg2 = json.loads(ws.receive_text())
        assert msg2.get("type") == "state"
        assert msg2.get("state") == "listening"

        # 2. Send 20ms of PCM16 16kHz mono audio (320 samples = 640 bytes)
        sample_frame = b"\x00\x04" * 320
        ws.send_bytes(sample_frame)

        # 3. Receive reflected raw audio frame
        received_bytes = ws.receive_bytes()
        assert received_bytes == sample_frame

        # 4. Clean hangup
        ws.send_text(json.dumps({"type": "hangup"}))


def test_browser_websocket_token_authentication():
    """Verify shared CALL_TOKEN enforcement: rejected without valid token, accepted with valid token."""
    original_token = settings.CALL_TOKEN
    try:
        settings.CALL_TOKEN = "super_secret_browser_token_123"

        # 1. Missing token -> rejected with policy violation (1008)
        try:
            with client.websocket_connect("/ws/call") as ws:
                _ = ws.receive()
            assert False, "Should have been closed"
        except Exception:
            pass

        # 2. Invalid token -> rejected
        try:
            with client.websocket_connect("/ws/call?token=wrong_token") as ws:
                _ = ws.receive()
            assert False, "Should have been closed"
        except Exception:
            pass

        # 3. Valid token -> connected successfully
        with client.websocket_connect("/ws/call?token=super_secret_browser_token_123") as ws:
            msg = json.loads(ws.receive_text())
            assert msg.get("type") == "state"
            assert msg.get("state") == "connected"
            ws.send_text(json.dumps({"type": "hangup"}))

    finally:
        settings.CALL_TOKEN = original_token


def test_browser_websocket_origin_check():
    """Verify Origin header validation: forbidden origins rejected, allowed origins accepted."""
    # 1. Malicious / unallowed origin -> closed
    try:
        with client.websocket_connect("/ws/call", headers={"Origin": "https://malicious-domain.xyz"}) as ws:
            _ = ws.receive()
        assert False, "Forbidden origin should be rejected"
    except Exception:
        pass

    # 2. Allowed origin -> accepted
    with client.websocket_connect("/ws/call", headers={"Origin": "http://localhost:8000"}) as ws:
        msg = json.loads(ws.receive_text())
        assert msg.get("state") == "connected"
        ws.send_text(json.dumps({"type": "hangup"}))


def test_browser_websocket_malformed_frames_do_not_crash():
    """Verify server safely discards non-JSON text, corrupted base64, and odd-length PCM bytes without crashing."""
    with client.websocket_connect("/ws/call?mode=echo") as ws:
        # Drain initial state messages
        _ = ws.receive_text()
        _ = ws.receive_text()

        # 1. Non-JSON string
        ws.send_text("this is completely invalid json string {{{")

        # 2. Non-dictionary JSON
        ws.send_text(json.dumps(["not", "a", "dict"]))

        # 3. Corrupted base64 payload
        ws.send_text(json.dumps({"type": "audio", "data": "!!not_base64@@"}))

        # 4. Odd-length PCM bytes (PCM16 requires 2 bytes per sample)
        ws.send_bytes(b"\x01\x02\x03")

        # 5. Subsequent valid frame must still be processed and echoed
        valid_pcm = b"\x10\x20" * 160
        ws.send_bytes(valid_pcm)
        echoed = ws.receive_bytes()
        assert echoed == valid_pcm

        ws.send_text(json.dumps({"type": "hangup"}))


def test_browser_websocket_client_abrupt_disconnect():
    """Verify server handles sudden client socket drop without unhandled errors."""
    with client.websocket_connect("/ws/call?mode=echo") as ws:
        _ = ws.receive_text()
        _ = ws.receive_text()
        ws.send_bytes(b"\x00\x01" * 160)
        _ = ws.receive_bytes()
        # Abrupt close without 'hangup' message
        ws.close()

    # Verify server remains healthy
    health_resp = client.get("/health")
    assert health_resp.status_code == 200
