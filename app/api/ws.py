"""Plivo WebSocket streaming endpoint with error resilience and bidirectional audio echo test support."""

import base64
import binascii
import json
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.logging import logger
from app.telephony.plivo_protocol import (
    create_play_audio_packet,
    parse_plivo_ws_message,
)

router = APIRouter(tags=["telephony_stream"])


@router.websocket("/ws/plivo/stream")
async def plivo_stream_websocket(
    websocket: WebSocket,
    mode: Optional[str] = None,  # ?mode=echo triggers bidirectional echo test
):
    """Bidirectional audio streaming WebSocket connected to active Plivo calls.

    Resilience guarantees:
    - Never crashes on missing 'start' event.
    - Never crashes on malformed/corrupted media frames or invalid base64.
    - Never crashes on unexpected client disconnection or mid-call WebSocket drop.
    """
    await websocket.accept()
    stream_id: Optional[str] = None
    call_id: Optional[str] = None
    has_received_start: bool = False
    frames_received = 0
    frames_echoed = 0
    is_echo_mode = (mode == "echo") or True  # Default to echo test in Phase 2

    logger.info(f"Plivo WebSocket connection established | Echo mode: {is_echo_mode}")

    try:
        while True:
            try:
                raw_msg = await websocket.receive_text()
            except (WebSocketDisconnect, ConnectionResetError, RuntimeError) as e:
                logger.info(f"Client disconnected mid-call: {e}")
                break

            if not raw_msg:
                continue

            try:
                data = parse_plivo_ws_message(raw_msg)
            except (json.JSONDecodeError, TypeError):
                logger.warning("Ignored non-JSON or malformed packet over Plivo WebSocket.")
                continue

            if not isinstance(data, dict):
                logger.warning(f"Ignored non-dictionary JSON payload: {type(data)}")
                continue

            event_type = data.get("event")

            if event_type == "start":
                has_received_start = True
                start_data = data.get("start")
                if isinstance(start_data, dict):
                    stream_id = data.get("streamId") or start_data.get("streamId")
                    call_id = start_data.get("callId")
                    media_format = start_data.get("mediaFormat", {})
                else:
                    stream_id = data.get("streamId")
                    media_format = {}
                logger.info(
                    f"Plivo Stream Started | StreamID: {stream_id} | CallID: {call_id} | Format: {media_format}"
                )

            elif event_type == "media":
                frames_received += 1
                media_info = data.get("media")

                # Edge Case 1: Missing 'start' event before media
                if not has_received_start:
                    logger.warning("Received 'media' frame prior to 'start' event. Processing safely.")

                # Edge Case 2: Malformed media frame structure
                if not isinstance(media_info, dict):
                    logger.warning("Ignored malformed 'media' block: not a dictionary.")
                    continue

                payload_b64 = media_info.get("payload")
                if not payload_b64 or not isinstance(payload_b64, str):
                    logger.warning("Ignored media frame: missing or non-string payload.")
                    continue

                # Edge Case 3: Malformed base64 payload
                try:
                    # Validate base64 payload decoding
                    decoded_bytes = base64.b64decode(payload_b64, validate=True)
                    if len(decoded_bytes) == 0:
                        logger.warning("Ignored empty audio frame.")
                        continue
                except (binascii.Error, ValueError) as b64_err:
                    logger.warning(f"Ignored corrupted base64 audio payload: {b64_err}")
                    continue

                if is_echo_mode:
                    try:
                        outbound_packet = create_play_audio_packet(
                            payload_b64=payload_b64,
                            content_type="audio/x-mulaw",
                            sample_rate=8000,
                        )
                        await websocket.send_text(outbound_packet)
                        frames_echoed += 1
                        if frames_echoed % 100 == 0:
                            logger.info(f"Echo test active: echoed {frames_echoed} frames to Plivo.")
                    except (WebSocketDisconnect, ConnectionResetError, RuntimeError):
                        logger.info("WebSocket closed while sending outbound echo frame.")
                        break

            elif event_type == "dtmf":
                dtmf_data = data.get("dtmf", {})
                digit = dtmf_data.get("digit") if isinstance(dtmf_data, dict) else None
                logger.info(f"DTMF Digit detected from caller: {digit}")

            elif event_type == "stop":
                logger.info(
                    f"Plivo Stream Stopped | StreamID: {stream_id} | Frames received: {frames_received} | Echoed: {frames_echoed}"
                )
                break

            else:
                logger.warning(f"Ignored unrecognized Plivo event: '{event_type}'")

    except WebSocketDisconnect:
        logger.info(f"Plivo WebSocket disconnected cleanly | StreamID: {stream_id}")
    except Exception as e:
        logger.error(f"Handled error in Plivo WebSocket session: {e}", exc_info=True)
    finally:
        logger.info(
            f"Stream session closed | StreamID: {stream_id} | Total received: {frames_received} | Total echoed: {frames_echoed}"
        )
