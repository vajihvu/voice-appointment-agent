"""Unit tests for phone agent LLM tools."""

from datetime import date, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.tools import execute_tool, get_tool_definitions


@pytest.mark.asyncio
async def test_tool_definitions():
    tools = get_tool_definitions()
    names = [t["function"]["name"] for t in tools]
    assert "check_slots" in names
    assert "book_appointment" in names
    assert "cancel_appointment" in names
    assert "transfer_to_human" in names
    assert "send_confirmation_sms" in names


@pytest.mark.asyncio
async def test_check_slots_execution(db_session: AsyncSession):
    tomorrow = str(date.today() + timedelta(days=1))
    res = await execute_tool(
        db_session=db_session,
        tool_name="check_slots",
        arguments_json=f'{{"date": "{tomorrow}"}}',
    )
    assert "available_slots" in res
    assert len(res["available_slots"]) > 0


@pytest.mark.asyncio
async def test_book_appointment_execution(db_session: AsyncSession):
    tomorrow = str(date.today() + timedelta(days=1))
    res = await execute_tool(
        db_session=db_session,
        tool_name="book_appointment",
        arguments_json=(
            f'{{"name": "John Doe", "phone": "+919876543210", '
            f'"date": "{tomorrow}", "slot": "10:00", "service": "Routine Cleaning"}}'
        ),
    )
    assert res.get("status") == "success"
    assert res.get("name") == "John Doe"
    assert "appointment_id" in res


@pytest.mark.asyncio
async def test_cancel_appointment_execution(db_session: AsyncSession):
    tomorrow = str(date.today() + timedelta(days=1))
    # 1. Book
    book_res = await execute_tool(
        db_session=db_session,
        tool_name="book_appointment",
        arguments_json=(
            f'{{"name": "Jane Doe", "phone": "+919876543210", '
            f'"date": "{tomorrow}", "slot": "11:00", "service": "Consultation"}}'
        ),
    )
    app_id = book_res["appointment_id"]

    # 2. Cancel
    cancel_res = await execute_tool(
        db_session=db_session,
        tool_name="cancel_appointment",
        arguments_json=f'{{"appointment_id": "{app_id}"}}',
    )
    assert cancel_res.get("status") == "success"


@pytest.mark.asyncio
async def test_transfer_to_human_execution(db_session: AsyncSession):
    res = await execute_tool(
        db_session=db_session,
        tool_name="transfer_to_human",
        arguments_json='{"reason": "Severe toothache and swelling"}',
    )
    assert res.get("status") == "transfer_initiated"
    assert "destination_number" in res
