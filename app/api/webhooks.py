"""Plivo Telephony Webhook endpoints for call answering, fallback, and status tracking."""

from typing import Optional

from fastapi import APIRouter, Depends, Form, Request, Response

from app.core.config import get_settings
from app.core.logging import logger, mask_phone_number
from app.core.security import verify_plivo_webhook_request
from app.db.connection import AsyncSessionLocal
from app.db.repository import create_or_get_call, finalize_call
from app.telephony.plivo_xml import generate_speak_xml, generate_stream_xml

router = APIRouter(prefix="/webhook/plivo", tags=["plivo_webhooks"])
settings = get_settings()


def _build_ws_url(base_url: str, mode: Optional[str] = None) -> str:
    """Converts an HTTP/HTTPS base URL into a WS/WSS URL pointing to the stream endpoint."""
    cleaned = base_url.rstrip("/")
    if cleaned.startswith("https://"):
        ws_base = "wss://" + cleaned[len("https://"):]
    elif cleaned.startswith("http://"):
        ws_base = "ws://" + cleaned[len("http://"):]
    else:
        ws_base = f"wss://{cleaned}"

    ws_url = f"{ws_base}/ws/plivo/stream"
    if mode:
        ws_url += f"?mode={mode}"
    return ws_url


@router.post("/answer")
async def plivo_answer_webhook(
    request: Request,
    call_uuid: Optional[str] = Form(None, alias="CallUUID"),
    from_number: Optional[str] = Form(None, alias="From"),
    to_number: Optional[str] = Form(None, alias="To"),
    direction: Optional[str] = Form(None, alias="Direction"),
    mode: Optional[str] = None,  # Optional query param: ?mode=echo
    _auth: bool = Depends(verify_plivo_webhook_request),
):
    """Primary Answer URL invoked by Plivo when an inbound call arrives."""
    caller_phone = from_number or "unknown"
    logger.info(
        f"Inbound call received | CallUUID: {call_uuid} | From: {mask_phone_number(caller_phone)} | To: {mask_phone_number(to_number)} | Mode: {mode or 'standard'}"
    )

    # Persist initial call session record in SQLite
    try:
        async with AsyncSessionLocal() as db:
            await create_or_get_call(
                session=db,
                caller_phone=caller_phone,
                plivo_call_uuid=call_uuid,
            )
    except Exception as e:
        logger.error(f"Error persisting initial call record: {e}")

    # Determine public WebSocket URL (using BASE_URL from settings or request host)
    base_url = settings.BASE_URL if settings.BASE_URL != "http://localhost:8000" else str(request.base_url)
    ws_url = _build_ws_url(base_url, mode=mode)
    logger.info(f"Returning Plivo Stream XML pointing to: {ws_url}")

    xml_response = generate_stream_xml(
        websocket_url=ws_url,
        bidirectional=True,
        keep_call_alive=True,
        content_type="audio/x-mulaw;rate=8000",
    )

    return Response(content=xml_response, media_type="application/xml")


@router.post("/fallback")
async def plivo_fallback_webhook(
    call_uuid: Optional[str] = Form(None, alias="CallUUID"),
):
    """Fallback webhook URL if primary answer fails."""
    logger.error(f"Plivo fallback webhook triggered for CallUUID: {call_uuid}")
    xml = generate_speak_xml("We are currently experiencing technical difficulties. Please call back in a few minutes.")
    return Response(content=xml, media_type="application/xml")


@router.post("/hangup")
async def plivo_hangup_webhook(
    call_uuid: Optional[str] = Form(None, alias="CallUUID"),
    duration: Optional[float] = Form(None, alias="Duration"),
    call_status: Optional[str] = Form(None, alias="CallStatus"),
):
    """Hangup callback invoked by Plivo when call disconnects."""
    logger.info(f"Plivo hangup callback | CallUUID: {call_uuid} | Status: {call_status} | Duration: {duration}s")
    if call_uuid:
        try:
            async with AsyncSessionLocal() as db:
                await finalize_call(
                    session=db,
                    call_id=call_uuid,
                    status=call_status or "completed",
                )
        except Exception as e:
            logger.warning(f"Could not finalize call by CallUUID in hangup webhook: {e}")
    return {"status": "ok"}
