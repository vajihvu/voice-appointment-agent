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

    # 1. Unconfirmed phone -> returns needs_confirmation and does NOT write to database
    res_unconfirmed = await execute_tool(
        db_session=db_session,
        tool_name="book_appointment",
        arguments_json=(
            f'{{"name": "John Doe", "phone": "+919876543210", '
            f'"date": "{tomorrow}", "slot": "10:00", "service": "Routine Cleaning", "phone_confirmed": false}}'
        ),
    )
    assert res_unconfirmed.get("status") == "needs_confirmation"
    assert "confirm" in res_unconfirmed.get("message", "").lower()

    # 2. Invalid phone number -> returns needs_phone
    res_invalid_phone = await execute_tool(
        db_session=db_session,
        tool_name="book_appointment",
        arguments_json=(
            f'{{"name": "John Doe", "phone": "12345", '
            f'"date": "{tomorrow}", "slot": "10:00", "service": "Routine Cleaning", "phone_confirmed": true}}'
        ),
    )
    assert res_invalid_phone.get("status") == "needs_phone"

    # 3. Confirmed phone -> successfully books appointment
    res_confirmed = await execute_tool(
        db_session=db_session,
        tool_name="book_appointment",
        arguments_json=(
            f'{{"name": "John Doe", "phone": "+919876543210", '
            f'"date": "{tomorrow}", "slot": "10:00", "service": "Routine Cleaning", "phone_confirmed": true}}'
        ),
    )
    assert res_confirmed.get("status") == "success"
    assert res_confirmed.get("name") == "John Doe"
    assert "appointment_id" in res_confirmed


@pytest.mark.asyncio
async def test_cancel_appointment_execution(db_session: AsyncSession):
    tomorrow = str(date.today() + timedelta(days=1))
    # 1. Book with phone_confirmed=True
    book_res = await execute_tool(
        db_session=db_session,
        tool_name="book_appointment",
        arguments_json=(
            f'{{"name": "Jane Doe", "phone": "+919876543210", '
            f'"date": "{tomorrow}", "slot": "11:00", "service": "Consultation", "phone_confirmed": true}}'
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
    # Case 1: In a browser call without known phone, tool requests contact number
    res_no_phone = await execute_tool(
        db_session=db_session,
        tool_name="transfer_to_human",
        arguments_json='{"reason": "Severe toothache and swelling"}',
    )
    assert res_no_phone.get("status") == "needs_phone"
    assert "valid" in res_no_phone.get("message", "").lower()

    # Case 2: Invalid phone number format -> needs_phone
    res_bad_phone = await execute_tool(
        db_session=db_session,
        tool_name="transfer_to_human",
        arguments_json='{"reason": "Severe toothache and swelling", "phone": "not_a_phone"}',
    )
    assert res_bad_phone.get("status") == "needs_phone"

    # Case 3: Valid contact number provided but unconfirmed -> needs_confirmation
    res_unconfirmed = await execute_tool(
        db_session=db_session,
        tool_name="transfer_to_human",
        arguments_json='{"reason": "Severe toothache and swelling", "phone": "+919876543210", "phone_confirmed": false}',
    )
    assert res_unconfirmed.get("status") == "needs_confirmation"
    assert "confirm" in res_unconfirmed.get("message", "").lower()

    # Case 4: With valid contact number and phone_confirmed=true -> callback_requested
    res_confirmed = await execute_tool(
        db_session=db_session,
        tool_name="transfer_to_human",
        arguments_json='{"reason": "Severe toothache and swelling", "phone": "+919876543210", "phone_confirmed": true}',
    )
    assert res_confirmed.get("status") == "callback_requested"
    assert res_confirmed.get("phone") == "+919876543210"
    assert "notified" in res_confirmed.get("message", "").lower()


@pytest.mark.asyncio
async def test_send_confirmation_notification(db_session: AsyncSession):
    res = await execute_tool(
        db_session=db_session,
        tool_name="send_confirmation_sms",
        arguments_json='{"phone": "+919876543210", "appointment_id": "APT-TEST-001"}',
    )
    assert res.get("status") == "recorded"
    assert "database" in res.get("message", "").lower()
