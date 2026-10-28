"""Tests verifying the phone digit read-back confirmation flow.

The mock_llm must NOT auto-set phone_confirmed=true. These tests use a
ScriptedMockLLM that follows an explicit dialogue script:

  Test 1 (happy path):
    - Caller asks to book → LLM calls book_appointment with phone_confirmed=false
    - Tool returns needs_confirmation → LLM reads digits back
    - Caller says "yes" → LLM calls book_appointment with phone_confirmed=true
    - Assert: no DB row before confirmation, one row after.

  Test 2 (correction path):
    - Caller asks to book → LLM calls book_appointment with phone_confirmed=false
    - Tool returns needs_confirmation → LLM reads digits back
    - Caller says "no, it's a different number" → LLM does NOT book
    - Assert: no DB row at any point.
"""

import json
from datetime import date, timedelta
from typing import Any, AsyncGenerator, Dict, List, Optional

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent.session import CallSession
from app.db.models import Appointment
from app.db.repository import create_or_get_call
from app.llm.base import LLMMessage, LLMProvider, LLMResponseChunk
from app.tts.mock_tts import MockTTSProvider

TOMORROW = str(date.today() + timedelta(days=1))


class ScriptedMockLLM(LLMProvider):
    """LLM that returns pre-scripted responses in order.

    Each entry in `script` is either:
      - A dict with "tool_calls" key → emits tool calls
      - A dict with "text" key → emits plain text reply
    """

    def __init__(self, script: List[Dict[str, Any]]):
        self._script = list(script)
        self._index = 0

    async def chat_stream(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncGenerator[LLMResponseChunk, None]:
        if self._index >= len(self._script):
            yield LLMResponseChunk(
                delta_text="I have nothing more to say.",
                is_first_token=True,
                is_complete=True,
            )
            return

        entry = self._script[self._index]
        self._index += 1

        if "tool_calls" in entry:
            yield LLMResponseChunk(
                is_first_token=True,
                tool_calls=entry["tool_calls"],
                is_complete=True,
            )
        else:
            yield LLMResponseChunk(
                delta_text=entry.get("text", ""),
                is_first_token=True,
                is_complete=True,
            )


async def _count_appointments(session: AsyncSession) -> int:
    result = await session.execute(select(Appointment))
    return len(result.scalars().all())


async def _make_session(
    llm: ScriptedMockLLM,
    session_factory,
) -> CallSession:
    """Create a CallSession wired to the scripted LLM."""
    async with session_factory() as db:
        call_record = await create_or_get_call(
            session=db,
            caller_phone="+919876543210",
            external_call_id=None,
        )
        call_id = call_record.id

    received_bytes = 0

    async def send_audio(chunk: bytes) -> None:
        nonlocal received_bytes
        received_bytes += len(chunk)

    async def clear_audio() -> None:
        pass

    return CallSession(
        call_id=call_id,
        caller_phone="+919876543210",
        llm_provider=llm,
        tts_provider=MockTTSProvider(chunk_delay_sec=0.0),
        db_session_factory=session_factory,
        send_audio_callback=send_audio,
        clear_audio_callback=clear_audio,
    )


@pytest.mark.asyncio
async def test_phone_readback_confirmed_then_booked(async_engine):
    """First booking attempt is unconfirmed; after digit read-back and 'yes', booking succeeds."""
    session_factory = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    # Script: 4 LLM invocations
    # 1. User says "book" → LLM emits book_appointment with phone_confirmed=false
    # 2. Tool returns needs_confirmation → LLM reads digits back (text reply)
    # 3. User says "yes" → LLM emits book_appointment with phone_confirmed=true
    # 4. Tool returns success → LLM confirms booking (text reply)
    script = [
        # Turn 1: LLM response to user's booking request
        {
            "tool_calls": [
                {
                    "id": "call_1",
                    "name": "book_appointment",
                    "arguments": json.dumps({
                        "name": "Alice Smith",
                        "phone": "+919876543210",
                        "date": TOMORROW,
                        "slot": "10:00",
                        "service": "Dental Cleaning",
                        "phone_confirmed": False,
                    }),
                }
            ]
        },
        # Turn 1 continued: LLM's response after tool returns needs_confirmation
        {
            "text": "Let me confirm your phone number. Is it 9-8-7-6-5-4-3-2-1-0?"
        },
        # Turn 2: LLM response after user says "yes"
        {
            "tool_calls": [
                {
                    "id": "call_2",
                    "name": "book_appointment",
                    "arguments": json.dumps({
                        "name": "Alice Smith",
                        "phone": "+919876543210",
                        "date": TOMORROW,
                        "slot": "10:00",
                        "service": "Dental Cleaning",
                        "phone_confirmed": True,
                    }),
                }
            ]
        },
        # Turn 2 continued: LLM's response after tool returns success
        {
            "text": "Your appointment has been booked for Alice Smith tomorrow at 10:00."
        },
    ]

    llm = ScriptedMockLLM(script)
    session = await _make_session(llm, session_factory)

    # Turn 1: "I'd like to book an appointment"
    await session.process_caller_turn(
        transcript="I'd like to book an appointment for dental cleaning tomorrow at 10 AM. My name is Alice Smith and phone is 9876543210.",
    )

    # After turn 1: phone was NOT confirmed, so no appointment row must exist
    async with session_factory() as db:
        count_before = await _count_appointments(db)
    assert count_before == 0, f"Expected 0 appointments before confirmation, got {count_before}"

    # Turn 2: Caller confirms "yes"
    await session.process_caller_turn(
        transcript="Yes, that's correct.",
    )

    # After turn 2: phone was confirmed, appointment must exist
    async with session_factory() as db:
        count_after = await _count_appointments(db)
    assert count_after == 1, f"Expected 1 appointment after confirmation, got {count_after}"

    await session.end_call()


@pytest.mark.asyncio
async def test_phone_readback_rejected_no_booking(async_engine):
    """Caller says 'no' when asked to confirm phone — nothing is written."""
    session_factory = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    # Script: 3 LLM invocations
    # 1. User says "book" → LLM emits book_appointment with phone_confirmed=false
    # 2. Tool returns needs_confirmation → LLM reads digits back (text reply)
    # 3. User says "no, wrong number" → LLM says "please provide the correct number" (no tool call)
    script = [
        # Turn 1: LLM response to user's booking request
        {
            "tool_calls": [
                {
                    "id": "call_1",
                    "name": "book_appointment",
                    "arguments": json.dumps({
                        "name": "Bob Jones",
                        "phone": "+919876543210",
                        "date": TOMORROW,
                        "slot": "11:00",
                        "service": "Consultation",
                        "phone_confirmed": False,
                    }),
                }
            ]
        },
        # Turn 1 continued: LLM's response after tool returns needs_confirmation
        {
            "text": "Let me confirm your phone number. Is it 9-8-7-6-5-4-3-2-1-0?"
        },
        # Turn 2: LLM response after user says "no"
        {
            "text": "I understand, could you please provide the correct phone number?"
        },
    ]

    llm = ScriptedMockLLM(script)
    session = await _make_session(llm, session_factory)

    # Turn 1: Booking request
    await session.process_caller_turn(
        transcript="Book an appointment for Bob Jones, consultation tomorrow at 11 AM. Phone 9876543210.",
    )

    # After turn 1: no appointment
    async with session_factory() as db:
        count_mid = await _count_appointments(db)
    assert count_mid == 0, f"Expected 0 appointments after unconfirmed attempt, got {count_mid}"

    # Turn 2: Caller rejects
    await session.process_caller_turn(
        transcript="No, that's the wrong number.",
    )

    # After turn 2: still no appointment
    async with session_factory() as db:
        count_end = await _count_appointments(db)
    assert count_end == 0, f"Expected 0 appointments after rejection, got {count_end}"

    await session.end_call()

