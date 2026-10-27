"""Plivo WebSocket protocol definitions, JSON schemas, and packet builders."""

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class PlivoStreamStart:
    stream_id: str
    call_id: str
    media_format: str
    sample_rate: int
    raw_data: Dict[str, Any]


@dataclass
class PlivoMediaChunk:
    payload_b64: str
    chunk_index: Optional[int] = None
    timestamp: Optional[int] = None


def parse_plivo_ws_message(raw_json: str) -> Dict[str, Any]:
    """Parses an inbound JSON packet from Plivo WebSocket."""
    return json.loads(raw_json)


def create_play_audio_packet(
    payload_b64: str,
    content_type: str = "audio/x-mulaw",
    sample_rate: int = 8000,
) -> str:
    """Builds an outbound 'playAudio' JSON packet to play synthesized audio to the caller."""
    packet = {
        "event": "playAudio",
        "media": {
            "contentType": content_type,
            "sampleRate": sample_rate,
            "payload": payload_b64,
        },
    }
    return json.dumps(packet)


def create_clear_audio_packet(stream_id: str) -> str:
    """Builds an outbound 'clearAudio' JSON packet to immediately interrupt playback on Plivo."""
    packet = {
        "event": "clearAudio",
        "streamId": stream_id,
    }
    return json.dumps(packet)
