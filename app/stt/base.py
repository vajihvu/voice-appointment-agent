"""Speech-to-Text (STT) abstract base class and event definitions."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncGenerator


@dataclass
class STTEvent:
    """Represents a speech recognition event received from the STT provider."""
    text: str
    is_final: bool
    confidence: float = 1.0
    words_count: int = 0
    speech_final: bool = False  # VAD indication that caller stopped speaking


class STTProvider(ABC):
    """Abstract interface for swappable real-time streaming STT providers."""

    @abstractmethod
    async def start(self) -> None:
        """Initializes the streaming connection."""
        pass

    @abstractmethod
    async def send_audio(self, audio_chunk: bytes) -> None:
        """Sends raw audio frame (e.g. 20ms G.711 mu-law 8kHz) to the provider."""
        pass

    @abstractmethod
    async def receive_events(self) -> AsyncGenerator[STTEvent, None]:
        """Asynchronously yields STT transcription events."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Closes the streaming session cleanly."""
        pass
