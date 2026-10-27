"""Mock STT provider for unit tests and local simulation."""

import asyncio
from typing import AsyncGenerator, List, Optional

from app.stt.base import STTEvent, STTProvider


class MockSTTProvider(STTProvider):
    """Simulated STT provider that emits predetermined transcripts or responds to test queues."""

    def __init__(self, predefined_transcripts: Optional[List[str]] = None):
        self.predefined_transcripts = predefined_transcripts or []
        self._queue: asyncio.Queue[STTEvent] = asyncio.Queue()
        self._is_running = False

    async def start(self) -> None:
        self._is_running = True
        for transcript in self.predefined_transcripts:
            words = transcript.strip().split()
            # Push an interim event first, then final
            if len(words) > 1:
                await self._queue.put(
                    STTEvent(
                        text=words[0],
                        is_final=False,
                        confidence=0.95,
                        words_count=1,
                    )
                )
            await self._queue.put(
                STTEvent(
                    text=transcript,
                    is_final=True,
                    confidence=0.98,
                    words_count=len(words),
                    speech_final=True,
                )
            )

    async def feed_transcript(self, text: str, is_final: bool = True, speech_final: bool = True) -> None:
        """Helper for simulator to inject a transcript utterance."""
        words = text.strip().split()
        await self._queue.put(
            STTEvent(
                text=text,
                is_final=is_final,
                confidence=0.99,
                words_count=len(words),
                speech_final=speech_final,
            )
        )

    async def send_audio(self, audio_chunk: bytes) -> None:
        # In mock, receiving audio simulates audio packet consumption
        pass

    async def receive_events(self) -> AsyncGenerator[STTEvent, None]:
        while self._is_running or not self._queue.empty():
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=0.1)
                yield event
            except asyncio.TimeoutError:
                if not self._is_running and self._queue.empty():
                    break
                continue

    async def close(self) -> None:
        self._is_running = False
