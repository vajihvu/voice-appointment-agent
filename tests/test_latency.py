"""Unit tests for turn latency measurement using a deterministic fake clock."""


import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent.session import CallSession
from app.db.models import TurnLatency
from app.db.repository import create_or_get_call
from app.llm.base import LLMProvider, LLMResponseChunk
from app.tts.base import TTSAudioChunk, TTSProvider


class FakeClock:
    """Deterministic simulated clock for testing latency timestamps."""

    def __init__(self, start_time: float = 100.0):
        self.current_time = start_time

    def time(self) -> float:
        return self.current_time

    def advance(self, seconds: float) -> None:
        self.current_time += seconds


class LatencyControlledLLM(LLMProvider):
    """Mock LLM that advances the fake clock to simulate inference delay."""

    def __init__(self, fake_clock: FakeClock, delay_sec: float = 0.25):
        self.fake_clock = fake_clock
        self.delay_sec = delay_sec

    async def chat_stream(self, messages, tools=None):
        self.fake_clock.advance(self.delay_sec)  # Advance clock during LLM reasoning
        yield LLMResponseChunk(
            delta_text="Hello, how can I help you?",
            is_first_token=True,
            is_complete=True,
        )


class LatencyControlledTTS(TTSProvider):
    """Mock TTS that advances the fake clock before emitting the first audio byte."""

    def __init__(self, fake_clock: FakeClock, ttfb_sec: float = 0.15):
        self.fake_clock = fake_clock
        self.ttfb_sec = ttfb_sec

    async def synthesize_text(self, text: str):
        self.fake_clock.advance(self.ttfb_sec)  # Advance clock to simulate time to first audio byte
        yield TTSAudioChunk(
            audio_bytes=b"\xff" * 160,
            is_first_chunk=True,
            is_final=True,
            sample_rate=8000,
        )

    async def synthesize_stream(self, text_stream):
        async for _ in text_stream:
            self.fake_clock.advance(self.ttfb_sec)
            yield TTSAudioChunk(audio_bytes=b"\xff" * 160, is_first_chunk=True, is_final=True)


@pytest.mark.asyncio
async def test_strict_latency_measurement_with_fake_clock(async_engine, monkeypatch):
    """Verifies that TurnLatency is strictly computed as (T_first_audio_byte - T_speech_end).

    Timeline:
    - Caller speech ends at t = 1000.000
    - LLM takes 0.300s -> finishes at t = 1000.300
    - TTS takes 0.150s to synthesize first chunk -> first byte sent at t = 1000.450
    - Expected total turn latency = (1000.450 - 1000.000) * 1000 = 450.0 ms
    """
    fake_clock = FakeClock(start_time=1000.0)
    monkeypatch.setattr("time.time", fake_clock.time)

    session_factory = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_factory() as db:
        call = await create_or_get_call(session=db, caller_phone="+919876543210")
        call_id = call.id

    llm = LatencyControlledLLM(fake_clock=fake_clock, delay_sec=0.300)
    tts = LatencyControlledTTS(fake_clock=fake_clock, ttfb_sec=0.150)

    sent_audio_frames = []

    async def mock_send_audio(audio: bytes):
        sent_audio_frames.append(audio)

    session = CallSession(
        call_id=call_id,
        caller_phone="+919876543210",
        llm_provider=llm,
        tts_provider=tts,
        db_session_factory=session_factory,
        send_audio_callback=mock_send_audio,
    )

    t_speech_end = 1000.000
    # Process turn with speech end at t0
    reply = await session.process_caller_turn(
        transcript="Hello clinic receptionist",
        speech_end_timestamp=t_speech_end,
        stt_latency_ms=180.0,
    )

    assert reply == "Hello, how can I help you?"
    assert len(sent_audio_frames) == 1

    # Query logged turn latency record from DB
    async with session_factory() as db:
        stmt = select(TurnLatency).where(TurnLatency.call_id == call_id)
        res = await db.execute(stmt)
        turn = res.scalar_one_or_none()

        assert turn is not None
        assert turn.turn_index == 1
        assert turn.stt_latency_ms == 180.0
        # Check LLM latency = 300ms
        assert pytest.approx(turn.llm_latency_ms, abs=1.0) == 300.0
        # Check TTS latency = 150ms
        assert pytest.approx(turn.tts_latency_ms, abs=1.0) == 150.0
        # Check Total Latency: exactly (1000.450 - 1000.000) * 1000 = 450.0ms
        assert pytest.approx(turn.total_turn_latency_ms, abs=1.0) == 450.0
