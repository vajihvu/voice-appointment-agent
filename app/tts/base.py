"""Text-to-Speech (TTS) abstract base class and chunk representations."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncGenerator


@dataclass
class TTSAudioChunk:
    """Represents a chunk of synthesized telephony audio (G.711 mu-law, 8000Hz)."""
    audio_bytes: bytes
    is_first_chunk: bool = False
    is_final: bool = False
    sample_rate: int = 8000


class TTSProvider(ABC):
    """Abstract interface for swappable streaming TTS providers."""

    @abstractmethod
    async def synthesize_text(self, text: str) -> AsyncGenerator[TTSAudioChunk, None]:
        """Synthesizes a static string into streaming mu-law audio chunks."""
        pass

    @abstractmethod
    async def synthesize_stream(
        self, text_stream: AsyncGenerator[str, None]
    ) -> AsyncGenerator[TTSAudioChunk, None]:
        """Synthesizes an incoming token/sentence stream into streaming mu-law audio chunks."""
        pass
