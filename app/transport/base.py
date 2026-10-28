"""Abstract VoiceTransport interface decoupling conversational sessions from underlying protocols."""

from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, Dict


class VoiceTransport(ABC):
    """Abstract interface defining the audio and event transport for a voice session.

    Guarantees:
    - Audio is exchanged strictly as raw PCM16, 16 kHz mono frames (bytes).
    - Conversational state machine interacts solely through this abstraction,
      making the application transport-agnostic (Browser WebSocket, SIP trunk, Telephony).
    """

    @abstractmethod
    async def start(self) -> None:
        """Initializes the transport connection lifecycle."""
        pass

    @abstractmethod
    async def receive_audio(self) -> AsyncGenerator[bytes, None]:
        """Yields continuous raw PCM16 16kHz mono audio frames from the caller or microphone."""
        pass

    @abstractmethod
    async def send_audio(self, pcm_bytes: bytes) -> None:
        """Transmits a synthesized PCM16 16kHz mono audio chunk to the listener."""
        pass

    @abstractmethod
    async def clear_audio(self) -> None:
        """Signals the client to flush queued playback immediately for instant barge-in."""
        pass

    @abstractmethod
    async def send_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Transmits structured telemetry, transcript updates, or call state transitions."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Terminates the transport connection cleanly."""
        pass
