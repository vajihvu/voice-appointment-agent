"""Security module integrating Plivo's official SDK cryptographic HMAC-SHA256 signature validator."""

from typing import Any, Dict, Optional

from fastapi import Header, HTTPException, Request, status
from plivo.utils import validate_v3_signature

from app.core.config import get_settings
from app.core.logging import logger

settings = get_settings()


def reconstruct_public_url(request: Request, base_url: str) -> str:
    """Reconstructs the full public URL as called by Plivo behind a reverse proxy/ngrok.

    Includes the exact scheme, host, path, and query string (e.g. '?mode=echo')
    to ensure the signature verification input precisely matches what Plivo signed.
    """
    base = base_url.rstrip("/")
    path = request.url.path
    query = request.url.query
    if query:
        return f"{base}{path}?{query}"
    return f"{base}{path}"


def verify_signature_v3(
    method: str,
    uri: str,
    nonce: str,
    auth_token: str,
    signature: str,
    params: Optional[Dict[str, Any]] = None,
) -> bool:
    """Invokes Plivo's official SDK helper to validate the request signature."""
    try:
        return validate_v3_signature(
            method=method,
            uri=uri,
            nonce=nonce,
            auth_token=auth_token,
            v3_signature=signature,
            params=params or {},
        )
    except Exception as e:
        logger.error(f"Error during Plivo official signature validation: {e}")
        return False


async def verify_plivo_webhook_request(
    request: Request,
    x_plivo_signature_v3: Optional[str] = Header(None, alias="X-Plivo-Signature-V3"),
    x_plivo_signature_v3_nonce: Optional[str] = Header(None, alias="X-Plivo-Signature-V3-Nonce"),
) -> bool:
    """FastAPI dependency for verifying that an inbound webhook originated from Plivo.

    Fails closed: if verification is enabled, missing or invalid signatures return HTTP 401.
    """
    if not settings.ENABLE_WEBHOOK_SIGNATURE_VERIFICATION:
        logger.warning(
            "⚠️  SECURITY WARNING: PLIVO WEBHOOK SIGNATURE VERIFICATION IS DISABLED! "
            "ANY CALLER CAN TRIGGER WEBHOOKS. SET ENABLE_WEBHOOK_SIGNATURE_VERIFICATION=true IN PRODUCTION."
        )
        return True

    if not x_plivo_signature_v3 or not x_plivo_signature_v3_nonce:
        logger.warning("Rejected webhook request: Missing X-Plivo-Signature-V3 or Nonce header.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Plivo V3 signature headers",
        )

    # Reconstruct the exact public URL signed by Plivo behind ngrok
    public_url = reconstruct_public_url(request, settings.BASE_URL)

    # Extract form parameters for POST requests
    params = {}
    if request.method.upper() == "POST":
        try:
            form = await request.form()
            params = dict(form)
        except Exception as e:
            logger.warning(f"Could not parse form body for signature validation: {e}")

    is_valid = verify_signature_v3(
        method=request.method,
        uri=public_url,
        nonce=x_plivo_signature_v3_nonce,
        auth_token=settings.PLIVO_AUTH_TOKEN,
        signature=x_plivo_signature_v3,
        params=params,
    )

    if not is_valid:
        logger.warning(
            f"Rejected webhook request: Invalid Plivo V3 signature for {request.method} {public_url}"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Plivo webhook signature",
        )

    return True
