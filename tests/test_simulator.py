import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from simulator.call_simulator import LocalCallSimulator


@pytest.mark.asyncio
async def test_simulator_runs_dialogue(async_engine):
    """Verify simulator completes dialogue, invokes tools, and computes latency metrics."""
    session_factory = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    sim = LocalCallSimulator(
        caller_phone="+919876543210",
        db_session_factory=session_factory,
    )
    dialogue = [
        "Hi, what appointment slots do you have available tomorrow?",
        "Please book 10:00 AM for Alice for dental checkup.",
        "That's all, thank you!",
    ]
    session = await sim.run_dialogue(dialogue)

    assert session.turn_index == 3
    assert session.outcome == "booked"
    assert session.is_active is False
    assert len(session.full_transcript) == 6  # 3 user turns + 3 agent replies
    assert sim.received_audio_bytes > 0

