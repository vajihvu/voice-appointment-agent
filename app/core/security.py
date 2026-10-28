"""Security and authentication module for browser WebSocket connections."""

from typing import List, Optional

from fastapi import WebSocket, status

from app.core.config import get_settings
from app.core.logging import logger

settings = get_settings()


def is_origin_allowed(origin: Optional[str], allowed_origins: List[str]) -> bool:
    """Checks whether the client Origin header is in the allowlist.

    If origin is None or empty (e.g. native client, file://, or non-browser),
    it is allowed on localhost development.
    """
    if not origin:
        return True

    # Normalize origin
    origin_clean = origin.rstrip("/")
    for allowed in allowed_origins:
        if allowed.rstrip("/") == origin_clean:
            return True
    return False


async def verify_ws_connection(
    websocket: WebSocket,
    token: Optional[str] = None,
) -> bool:
    """Verifies that an incoming WebSocket connection complies with origin and shared token policies.

    Closes the connection immediately if verification fails.
    """
    origin = websocket.headers.get("origin")
    if not is_origin_allowed(origin, settings.ALLOWED_ORIGINS):
        logger.warning(f"Rejected WebSocket connection: Forbidden Origin '{origin}'")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Forbidden Origin")
        return False

    # Check shared token if configured
    expected_token = settings.CALL_TOKEN.strip()
    if expected_token:
        provided_token = token or websocket.query_params.get("token") or websocket.headers.get("x-call-token")
        if not provided_token or provided_token != expected_token:
            logger.warning("Rejected WebSocket connection: Invalid or missing authentication token")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Unauthorized")
            return False

    return True
