import asyncio
from datetime import date, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.models import Appointment, Base
from app.db.repository import seed_slots_for_date_range
from app.llm.tools import execute_tool

TEST_DB_PATH = Path("./test_concurrency_suite.db")


@pytest.mark.asyncio
async def test_concurrent_booking_race_condition():
    """Simulates 5 callers attempting to book the exact same slot concurrently.

    Uses a file-based SQLite database so each concurrent task operates on an
    independent physical database connection, testing real multi-connection ACID locking.

    Asserts that:
    1. Exactly one caller gets a confirmed appointment.
    2. All other 4 callers receive a conflict notification.
    3. The database strictly contains only 1 appointment record for that slot.
    """
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{TEST_DB_PATH.as_posix()}",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    target_date_obj = date.today() + timedelta(days=2)
    test_date = str(target_date_obj)
    target_slot = "14:00"

    # Pre-seed calendar slots for this test date so slots exist before concurrent bookings
    async with session_factory() as session:
        await seed_slots_for_date_range(session, target_date_obj, days=1)

    async def attempt_booking(caller_idx: int):
        async with session_factory() as session:
            return await execute_tool(
                db_session=session,
                tool_name="book_appointment",
                arguments_json=(
                    f'{{"name": "Caller {caller_idx}", "phone": "+91987654321{caller_idx}", '
                    f'"date": "{test_date}", "slot": "{target_slot}", "service": "Routine Cleaning", "phone_confirmed": true}}'
                ),
            )

    try:
        # Launch 5 concurrent booking attempts
        results = await asyncio.gather(*(attempt_booking(i) for i in range(5)))

        # Count successes and conflicts
        successes = [r for r in results if r.get("status") == "success"]
        conflicts = [r for r in results if r.get("status") == "conflict"]

        assert len(successes) == 1, f"Expected exactly 1 success, got {len(successes)}"
        assert len(conflicts) == 4, f"Expected 4 conflicts, got {len(conflicts)}"

        # Verify database state
        app_id = successes[0]["appointment_id"]
        async with session_factory() as session:
            stmt = select(Appointment)
            res = await session.execute(stmt)
            all_apps = res.scalars().all()
            matching = [a for a in all_apps if a.id == app_id]
            assert len(matching) == 1, f"Appointment {app_id} not found in DB! Found: {[a.id for a in all_apps]}"
            assert matching[0].status == "confirmed"
            assert matching[0].start_time == target_slot

    finally:
        await engine.dispose()
        if TEST_DB_PATH.exists():
            try:
                TEST_DB_PATH.unlink()
            except Exception:
                pass


