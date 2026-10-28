"""Browser Voice WebSocket streaming endpoint with PCM16 16kHz framing, origin check, and echo test support."""

from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import get_settings
from app.core.logging import logger
from app.core.security import verify_ws_connection
from app.transport.browser_transport import BrowserVoiceTransport

router = APIRouter(tags=["browser_voice_transport"])
settings = get_settings()


@router.websocket("/ws/call")
async def browser_call_websocket(
    websocket: WebSocket,
    token: Optional[str] = None,
    mode: Optional[str] = None,  # ?mode=echo triggers audio loopback/latency echo test
):
    """Bidirectional WebSocket endpoint connecting browser Web Audio to the voice agent.

    Guarantees:
    - Audio Format: PCM16 16 kHz mono (binary frames).
    - Origin verification and optional shared token authorization.
    - Never crashes on mid-call disconnect, malformed JSON, or corrupted audio frames.
    - Immediate playback flushing on 'clear' control packets (barge-in).
    """
    # 1. Security verification (Origin check & optional shared token)
    origin_ok = await verify_ws_connection(websocket, token=token)
    if not origin_ok:
        return

    await websocket.accept()
    transport = BrowserVoiceTransport(websocket)
    await transport.start()

    is_echo_mode = (mode == "echo") or True  # Default to echo test in Phase 2
    frames_received = 0
    frames_echoed = 0
    call_id = f"call-{id(websocket)}"

    logger.info(f"Browser voice stream connected | Call ID: {call_id} | Echo mode: {is_echo_mode}")

    # Notify browser that connection is established and agent is ready
    await transport.send_event("state", {"state": "connected", "call_id": call_id})
    await transport.send_event("state", {"state": "listening"})

    try:
        async for audio_chunk in transport.receive_audio():
            frames_received += 1

            if is_echo_mode:
                # Echo raw PCM16 16kHz audio frame back to browser for live loopback testing
                await transport.send_audio(audio_chunk)
                frames_echoed += 1

    except WebSocketDisconnect:
        logger.info(f"Browser client disconnected cleanly | Call ID: {call_id}")
    except Exception as e:
        logger.error(f"Handled error in browser voice session: {e}", exc_info=True)
    finally:
        await transport.close()
        logger.info(
            f"Browser call closed | Call ID: {call_id} | Frames received: {frames_received} | Echoed: {frames_echoed}"
        )
