"""Browser WebSocket implementation of the VoiceTransport interface."""

import asyncio
import base64
import binascii
import json
from typing import Any, AsyncGenerator, Dict, Optional

from fastapi import WebSocket, WebSocketDisconnect

from app.core.logging import logger
from app.transport.base import VoiceTransport


class BrowserVoiceTransport(VoiceTransport):
    """Voice transport over a bidirectional WebSocket connecting a web browser client.

    Audio Format:
    - Inbound: PCM16 16kHz mono (sent as raw binary WebSocket frames, or base64 text)
    - Outbound: PCM16 16kHz mono (sent as raw binary WebSocket frames)
    - Control/Events: JSON text frames (e.g. `{"type": "clear"}`)
    """

    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self._is_connected = False
        self._audio_queue: asyncio.Queue[Optional[bytes]] = asyncio.Queue()
        self._reader_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Starts the transport background reader."""
        self._is_connected = True
        self._reader_task = asyncio.create_task(self._read_incoming_loop())

    async def _read_incoming_loop(self) -> None:
        """Continuous listener for inbound WebSocket frames (binary PCM audio or JSON control)."""
        try:
            while self._is_connected:
                try:
                    message = await self.websocket.receive()
                except (WebSocketDisconnect, ConnectionResetError, RuntimeError) as e:
                    logger.info(f"Browser client disconnected: {e}")
                    break

                if "bytes" in message and message["bytes"]:
                    # Inbound binary audio frame (raw PCM16 16kHz mono)
                    raw_bytes = message["bytes"]
                    if len(raw_bytes) % 2 != 0:
                        logger.warning(f"Discarding odd-length PCM frame ({len(raw_bytes)} bytes)")
                        continue
                    await self._audio_queue.put(raw_bytes)

                elif "text" in message and message["text"]:
                    raw_text = message["text"].strip()
                    if not raw_text:
                        continue

                    try:
                        data = json.loads(raw_text)
                    except json.JSONDecodeError:
                        logger.warning("Ignored non-JSON text frame on /ws/call")
                        continue

                    if not isinstance(data, dict):
                        logger.warning("Ignored non-dictionary JSON frame")
                        continue

                    msg_type = data.get("type")

                    if msg_type in ("hangup", "stop"):
                        logger.info("Received client hangup message.")
                        break

                    elif msg_type == "audio":
                        # Base64 fallback format
                        payload_b64 = data.get("data")
                        if payload_b64 and isinstance(payload_b64, str):
                            try:
                                decoded = base64.b64decode(payload_b64, validate=True)
                                if len(decoded) % 2 == 0:
                                    await self._audio_queue.put(decoded)
                            except (binascii.Error, ValueError):
                                logger.warning("Ignored corrupted base64 audio payload")

                    elif msg_type == "ping":
                        await self.send_event("pong", {})

                    else:
                        logger.debug(f"Unhandled client message type: {msg_type}")

        except Exception as e:
            logger.error(f"Error in BrowserVoiceTransport read loop: {e}", exc_info=True)
        finally:
            self._is_connected = False
            await self._audio_queue.put(None)  # Sentinel to terminate receive_audio

    async def receive_audio(self) -> AsyncGenerator[bytes, None]:
        """Yields continuous PCM16 16kHz audio chunks until client disconnects."""
        while True:
            chunk = await self._audio_queue.get()
            if chunk is None:
                break
            yield chunk

    async def send_audio(self, pcm_bytes: bytes) -> None:
        """Sends raw PCM16 16kHz mono audio bytes directly to the browser."""
        if not self._is_connected:
            return
        try:
            await self.websocket.send_bytes(pcm_bytes)
        except (WebSocketDisconnect, ConnectionResetError, RuntimeError):
            self._is_connected = False

    async def clear_audio(self) -> None:
        """Sends immediate barge-in interrupt signal to flush client audio buffers."""
        if not self._is_connected:
            return
        try:
            await self.websocket.send_text(json.dumps({"type": "clear"}))
        except (WebSocketDisconnect, ConnectionResetError, RuntimeError):
            self._is_connected = False

    async def send_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Sends a JSON control or state packet to the browser client."""
        if not self._is_connected:
            return
        payload = {"type": event_type, **data}
        try:
            await self.websocket.send_text(json.dumps(payload))
        except (WebSocketDisconnect, ConnectionResetError, RuntimeError):
            self._is_connected = False

    async def close(self) -> None:
        """Closes the WebSocket connection."""
        self._is_connected = False
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
        try:
            await self.websocket.close()
        except Exception:
            pass
