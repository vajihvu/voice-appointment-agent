"""Unit and integration tests for Plivo webhooks, SDK signature verification, and WebSocket resilience."""

import json
import xml.etree.ElementTree as ET

from fastapi.testclient import TestClient
from plivo.utils import validate_v3_signature
from plivo.utils.signature_v3 import construct_post_url, get_signature_v3

from app.core.config import get_settings
from app.main import app

client = TestClient(app)
settings = get_settings()


def generate_sdk_signature(uri: str, method: str, params: dict, nonce: str, auth_token: str) -> str:
    """Helper generating genuine Plivo V3 signature using Plivo's official SDK internals."""
    if method.upper() == "POST":
        base_url = construct_post_url(uri, params).decode("utf-8")
    else:
        from plivo.utils.signature_v3 import construct_get_url
        base_url = construct_get_url(uri, params).decode("utf-8")

    sig_bytes = get_signature_v3(auth_token, base_url, nonce)
    return sig_bytes.decode("utf-8") if isinstance(sig_bytes, bytes) else sig_bytes


def test_official_plivo_signature_validation_positive():
    """Verify that legitimate signatures generated with Plivo SDK validate successfully."""
    uri = "https://example.com/webhook/plivo/answer?mode=echo"
    nonce = "test_nonce_987654"
    auth_token = "secret_plivo_auth_token_123"
    params = {
        "CallUUID": "uuid-12345",
        "From": "+919876543210",
        "To": "+12025550143",
    }

    valid_sig = generate_sdk_signature(uri, "POST", params, nonce, auth_token)

    # Validate using official Plivo SDK validator
    assert validate_v3_signature(
        method="POST",
        uri=uri,
        nonce=nonce,
        auth_token=auth_token,
        v3_signature=valid_sig,
        params=params,
    ) is True


def test_official_plivo_signature_validation_negative_tampering():
    """Negative tests: verify tampered parameters, wrong nonce, wrong URL, and wrong auth token are rejected."""
    uri = "https://example.com/webhook/plivo/answer?mode=echo"
    nonce = "test_nonce_987654"
    auth_token = "secret_plivo_auth_token_123"
    params = {"CallUUID": "uuid-12345", "From": "+919876543210"}

    genuine_sig = generate_sdk_signature(uri, "POST", params, nonce, auth_token)

    # 1. Tampered parameters (e.g. caller ID injection)
    tampered_params = {"CallUUID": "uuid-12345", "From": "+919999999999"}
    assert validate_v3_signature(
        method="POST",
        uri=uri,
        nonce=nonce,
        auth_token=auth_token,
        v3_signature=genuine_sig,
        params=tampered_params,
    ) is False

    # 2. Tampered nonce
    assert validate_v3_signature(
        method="POST",
        uri=uri,
        nonce="tampered_nonce",
        auth_token=auth_token,
        v3_signature=genuine_sig,
        params=params,
    ) is False

    # 3. Tampered URI
    assert validate_v3_signature(
        method="POST",
        uri="https://attacker.com/webhook/plivo/answer?mode=echo",
        nonce=nonce,
        auth_token=auth_token,
        v3_signature=genuine_sig,
        params=params,
    ) is False

    # 4. Wrong Auth Token
    assert validate_v3_signature(
        method="POST",
        uri=uri,
        nonce=nonce,
        auth_token="wrong_auth_token",
        v3_signature=genuine_sig,
        params=params,
    ) is False


def test_webhook_endpoint_fails_closed_when_signature_missing_or_invalid():
    """Verify webhook endpoint rejects requests with missing or forged signature headers when verification is active."""
    # Ensure verification is enabled
    settings.ENABLE_WEBHOOK_SIGNATURE_VERIFICATION = True

    # 1. Missing headers -> 401 Unauthorized
    resp_missing = client.post(
        "/webhook/plivo/answer",
        data={"CallUUID": "call-1", "From": "+919876543210"},
    )
    assert resp_missing.status_code == 401
    assert "Missing Plivo V3 signature headers" in resp_missing.json()["detail"]

    # 2. Forged signature -> 401 Unauthorized
    resp_forged = client.post(
        "/webhook/plivo/answer",
        data={"CallUUID": "call-1", "From": "+919876543210"},
        headers={
            "X-Plivo-Signature-V3": "forged_signature_xyz==",
            "X-Plivo-Signature-V3-Nonce": "fake_nonce_123",
        },
    )
    assert resp_forged.status_code == 401
    assert "Invalid Plivo webhook signature" in resp_forged.json()["detail"]


def test_webhook_endpoint_succeeds_with_valid_signature():
    """Verify webhook endpoint accepts genuinely signed requests and returns Stream XML."""
    settings.ENABLE_WEBHOOK_SIGNATURE_VERIFICATION = True
    settings.PLIVO_AUTH_TOKEN = "test_auth_token_secret"
    settings.BASE_URL = "http://testserver"

    uri = "http://testserver/webhook/plivo/answer"
    nonce = "valid_nonce_54321"
    params = {"CallUUID": "call-valid-123", "From": "+919876543210", "To": "+12025550143", "Direction": "inbound"}

    genuine_sig = generate_sdk_signature(uri, "POST", params, nonce, settings.PLIVO_AUTH_TOKEN)

    response = client.post(
        "/webhook/plivo/answer",
        data=params,
        headers={
            "X-Plivo-Signature-V3": genuine_sig,
            "X-Plivo-Signature-V3-Nonce": nonce,
        },
    )

    assert response.status_code == 200
    assert "application/xml" in response.headers["content-type"]
    root = ET.fromstring(response.content)
    assert root.tag == "Response"
    stream = root.find("Stream")
    assert stream is not None
    assert stream.attrib["bidirectional"] == "true"
    assert stream.attrib["contentType"] == "audio/x-mulaw;rate=8000"


def test_plivo_websocket_bidirectional_echo_loop():
    """Verify WebSocket echo test reflects inbound audio frames back as playAudio."""
    with client.websocket_connect("/ws/plivo/stream?mode=echo") as ws:
        # 1. Send start event
        start_event = {
            "event": "start",
            "streamId": "stream-echo-001",
            "start": {
                "streamId": "stream-echo-001",
                "callId": "call-uuid-001",
                "mediaFormat": {"encoding": "audio/x-mulaw", "sampleRate": 8000},
            },
        }
        ws.send_text(json.dumps(start_event))

        # 2. Send media frame with valid base64 mu-law audio payload
        test_payload_b64 = "AP//AP//AP//AP//"
        media_event = {
            "event": "media",
            "media": {
                "payload": test_payload_b64,
                "chunk": 1,
                "timestamp": 12345678,
            },
        }
        ws.send_text(json.dumps(media_event))

        # 3. Receive reflected playAudio event
        response_text = ws.receive_text()
        response_data = json.loads(response_text)

        assert response_data.get("event") == "playAudio"
        media = response_data.get("media", {})
        assert media.get("contentType") == "audio/x-mulaw"
        assert media.get("sampleRate") == 8000
        assert media.get("payload") == test_payload_b64

        # 4. Clean shutdown
        ws.send_text(json.dumps({"event": "stop", "streamId": "stream-echo-001"}))


def test_websocket_missing_start_event_does_not_crash():
    """Verify server tolerates receiving media frames before any 'start' event without crashing."""
    with client.websocket_connect("/ws/plivo/stream?mode=echo") as ws:
        # Send media frame directly without preceding start
        media_event = {
            "event": "media",
            "media": {"payload": "AP//AP//", "chunk": 1},
        }
        ws.send_text(json.dumps(media_event))
        resp = json.loads(ws.receive_text())
        assert resp["event"] == "playAudio"
        ws.send_text(json.dumps({"event": "stop"}))


def test_websocket_malformed_media_frames_do_not_crash():
    """Verify server safely discards corrupted JSON, malformed media dictionaries, and bad base64."""
    with client.websocket_connect("/ws/plivo/stream?mode=echo") as ws:
        # 1. Non-dictionary JSON
        ws.send_text(json.dumps(["not", "a", "dict"]))

        # 2. Malformed media block (not a dict)
        ws.send_text(json.dumps({"event": "media", "media": "corrupted_string"}))

        # 3. Missing payload
        ws.send_text(json.dumps({"event": "media", "media": {"chunk": 1}}))

        # 4. Non-string payload
        ws.send_text(json.dumps({"event": "media", "media": {"payload": 12345}}))

        # 5. Invalid base64 characters
        ws.send_text(json.dumps({"event": "media", "media": {"payload": "!!invalid_base64@@"}}))

        # 6. Valid frame afterwards should still succeed
        valid_b64 = "AP//AP//"
        ws.send_text(json.dumps({"event": "media", "media": {"payload": valid_b64}}))
        resp = json.loads(ws.receive_text())
        assert resp["event"] == "playAudio"
        assert resp["media"]["payload"] == valid_b64

        ws.send_text(json.dumps({"event": "stop"}))


def test_websocket_client_abrupt_disconnect_mid_call():
    """Verify abrupt client termination mid-stream closes cleanly on the server without unhandled errors."""
    with client.websocket_connect("/ws/plivo/stream?mode=echo") as ws:
        ws.send_text(json.dumps({"event": "start", "streamId": "abrupt-drop"}))
        ws.send_text(json.dumps({"event": "media", "media": {"payload": "AP//AP//" }}))
        _ = ws.receive_text()
        # Abrupt close without sending 'stop'
        ws.close()
    # Server should continue serving requests normally
    health_resp = client.get("/health")
    assert health_resp.status_code == 200
