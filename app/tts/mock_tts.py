"""Mock TTS provider emitting synthetic 8kHz mu-law audio frames for testing and simulation."""

import asyncio
from typing import AsyncGenerator

from app.tts.base import TTSAudioChunk, TTSProvider


class MockTTSProvider(TTSProvider):
    """Generates synthetic G.711 mu-law frames (160 bytes per 20ms frame) for tests and simulation."""

    def __init__(self, chunk_delay_sec: float = 0.01):
        self.chunk_delay_sec = chunk_delay_sec
        # 160 bytes of silence / comfort tone in G.711 mu-law (0xFF represents quiet silence in mu-law)
        self.dummy_20ms_frame = b"\xff" * 160

    async def synthesize_text(self, text: str) -> AsyncGenerator[TTSAudioChunk, None]:
        # Approximate frame count based on word count (~4 words per second = 50 frames per second = ~12 frames per word)
        words = len(text.split())
        frame_count = max(3, words * 8)

        for i in range(frame_count):
            if self.chunk_delay_sec > 0:
                await asyncio.sleep(self.chunk_delay_sec)
            yield TTSAudioChunk(
                audio_bytes=self.dummy_20ms_frame,
                is_first_chunk=(i == 0),
                is_final=(i == frame_count - 1),
                sample_rate=8000,
            )

    async def synthesize_stream(
        self, text_stream: AsyncGenerator[str, None]
    ) -> AsyncGenerator[TTSAudioChunk, None]:
        first = True
        async for chunk in text_stream:
            if not chunk.strip():
                continue
            if self.chunk_delay_sec > 0:
                await asyncio.sleep(self.chunk_delay_sec)
            yield TTSAudioChunk(
                audio_bytes=self.dummy_20ms_frame,
                is_first_chunk=first,
                is_final=False,
                sample_rate=8000,
            )
            first = False
