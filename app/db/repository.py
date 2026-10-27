"""Database repository providing transactional operations for slots, bookings, calls, and latencies."""

from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import and_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger, mask_phone_number
from app.db.models import Appointment, Call, ScheduleSlot, TurnLatency


class SlotAlreadyBookedException(Exception):
    """Raised when an attempt is made to book an already occupied slot."""
    pass


class SlotNotFoundException(Exception):
    """Raised when the requested slot time or date is invalid."""
    pass


async def seed_slots_for_date_range(
    session: AsyncSession,
    start_date: date,
    days: int = 14,
    start_hour: int = 9,
    end_hour: int = 17,
    interval_minutes: int = 30,
) -> int:
    """Seeds default clinic calendar slots if they do not already exist."""
    slots_created = 0
    try:
        for day_offset in range(days):
            current_date = start_date + timedelta(days=day_offset)
            # Skip Sundays (weekday 6)
            if current_date.weekday() == 6:
                continue

            curr_time = datetime(current_date.year, current_date.month, current_date.day, start_hour, 0)
            end_time = datetime(current_date.year, current_date.month, current_date.day, end_hour, 0)

            while curr_time < end_time:
                next_time = curr_time + timedelta(minutes=interval_minutes)
                start_str = curr_time.strftime("%H:%M")
                end_str = next_time.strftime("%H:%M")

                stmt = select(ScheduleSlot).where(
                    and_(
                        ScheduleSlot.slot_date == current_date,
                        ScheduleSlot.start_time == start_str,
                    )
                )
                res = await session.execute(stmt)
                existing = res.scalar_one_or_none()

                if not existing:
                    slot = ScheduleSlot(
                        slot_date=current_date,
                        start_time=start_str,
                        end_time=end_str,
                        is_available=True,
                    )
                    session.add(slot)
                    slots_created += 1

                curr_time = next_time

        if slots_created > 0:
            await session.commit()
            logger.info(f"Seeded {slots_created} new calendar slots.")
    except IntegrityError:
        await session.rollback()
    return slots_created


async def get_available_slots(session: AsyncSession, target_date: date) -> List[str]:
    """Retrieves list of available start times for a given date."""
    stmt = select(ScheduleSlot.start_time).where(
        and_(
            ScheduleSlot.slot_date == target_date,
            ScheduleSlot.is_available.is_(True),
        )
    ).order_by(ScheduleSlot.start_time)
    result = await session.execute(stmt)
    slots = [row[0] for row in result.all()]
    if not slots:
        await seed_slots_for_date_range(session, target_date, days=1)
        result = await session.execute(stmt)
        slots = [row[0] for row in result.all()]
    return slots



async def book_appointment_tx(
    session: AsyncSession,
    customer_name: str,
    customer_phone: str,
    appointment_date: date,
    start_time: str,
    service_type: str = "General Checkup",
    call_id: Optional[str] = None,
    notes: Optional[str] = None,
) -> Appointment:
    """Atomically books an appointment within a transaction, preventing double booking.

    Raises:
        SlotAlreadyBookedException: if the slot is already taken.
    """
    try:
        # Check slot availability
        stmt = select(ScheduleSlot).where(
            and_(
                ScheduleSlot.slot_date == appointment_date,
                ScheduleSlot.start_time == start_time,
            )
        ).with_for_update()  # Lock row if supported
        res = await session.execute(stmt)
        slot = res.scalar_one_or_none()

        if slot and not slot.is_available:
            raise SlotAlreadyBookedException(
                f"Slot on {appointment_date} at {start_time} is already booked."
            )

        # Calculate end_time (default 30 mins later)
        try:
            start_dt = datetime.strptime(start_time, "%H:%M")
            end_time = (start_dt + timedelta(minutes=30)).strftime("%H:%M")
        except ValueError:
            end_time = start_time

        appointment = Appointment(
            call_id=call_id,
            customer_name=customer_name,
            customer_phone=customer_phone,
            appointment_date=appointment_date,
            start_time=start_time,
            end_time=end_time,
            service_type=service_type,
            status="confirmed",
            notes=notes,
        )
        session.add(appointment)
        await session.flush()  # Generates appointment.id and tests unique constraint

        # Update or create schedule slot
        if slot:
            slot.is_available = False
            slot.booked_by_name = customer_name
            slot.booked_by_phone = customer_phone
            slot.appointment_id = appointment.id
        else:
            new_slot = ScheduleSlot(
                slot_date=appointment_date,
                start_time=start_time,
                end_time=end_time,
                is_available=False,
                booked_by_name=customer_name,
                booked_by_phone=customer_phone,
                appointment_id=appointment.id,
            )
            session.add(new_slot)

        await session.commit()
        logger.info(
            f"Successfully booked appointment {appointment.id} for {customer_name} ({mask_phone_number(customer_phone)}) on {appointment_date} at {start_time}."
        )
        return appointment


    except IntegrityError as e:
        await session.rollback()
        logger.warning(f"Concurrency conflict: Slot on {appointment_date} at {start_time} was just booked by another caller.")
        raise SlotAlreadyBookedException(
            f"Slot on {appointment_date} at {start_time} is already booked."
        ) from e
    except Exception:
        await session.rollback()
        raise


async def cancel_appointment_tx(session: AsyncSession, appointment_id: str) -> bool:
    """Cancels an appointment and frees up its calendar slot."""
    stmt = select(Appointment).where(Appointment.id == appointment_id)
    res = await session.execute(stmt)
    appointment = res.scalar_one_or_none()

    if not appointment:
        return False

    appointment.status = "cancelled"

    # Free up slot
    slot_stmt = select(ScheduleSlot).where(
        and_(
            ScheduleSlot.slot_date == appointment.appointment_date,
            ScheduleSlot.start_time == appointment.start_time,
        )
    )
    slot_res = await session.execute(slot_stmt)
    slot = slot_res.scalar_one_or_none()
    if slot:
        slot.is_available = True
        slot.booked_by_name = None
        slot.booked_by_phone = None
        slot.appointment_id = None

    await session.commit()
    logger.info(f"Cancelled appointment {appointment_id} and freed schedule slot.")
    return True


def utc_now() -> datetime:
    """Returns a timezone-naive UTC datetime for SQLite compatibility."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def create_or_get_call(
    session: AsyncSession,
    caller_phone: str,
    plivo_call_uuid: Optional[str] = None,
) -> Call:
    """Creates a new Call session record."""
    call = Call(
        caller_phone=caller_phone,
        plivo_call_uuid=plivo_call_uuid,
        start_time=utc_now(),
        status="in_progress",
    )
    session.add(call)
    await session.commit()
    await session.refresh(call)
    return call


async def log_turn_latency(
    session: AsyncSession,
    call_id: str,
    turn_index: int,
    speaker: str,
    user_transcript: Optional[str] = None,
    agent_response: Optional[str] = None,
    tool_called: Optional[str] = None,
    stt_latency_ms: float = 0.0,
    llm_latency_ms: float = 0.0,
    tts_latency_ms: float = 0.0,
    total_turn_latency_ms: float = 0.0,
) -> TurnLatency:
    """Logs turn-by-turn performance latency metrics."""
    turn = TurnLatency(
        call_id=call_id,
        turn_index=turn_index,
        speaker=speaker,
        user_transcript=user_transcript,
        agent_response=agent_response,
        tool_called=tool_called,
        stt_latency_ms=stt_latency_ms,
        llm_latency_ms=llm_latency_ms,
        tts_latency_ms=tts_latency_ms,
        total_turn_latency_ms=total_turn_latency_ms,
    )
    session.add(turn)
    await session.commit()
    return turn


async def finalize_call(
    session: AsyncSession,
    call_id: str,
    status: str = "completed",
    outcome: Optional[str] = None,
    handoff_reason: Optional[str] = None,
    full_transcript: Optional[str] = None,
    sms_sent: bool = False,
) -> Optional[Call]:
    """Finalizes a call with outcome, end time, and duration."""
    stmt = select(Call).where(Call.id == call_id)
    res = await session.execute(stmt)
    call = res.scalar_one_or_none()

    if not call:
        return None

    call.end_time = utc_now()
    call.status = status
    call.outcome = outcome
    call.handoff_reason = handoff_reason
    if full_transcript:
        call.full_transcript = full_transcript
    call.sms_sent = sms_sent

    if call.start_time:
        call.total_duration_sec = (call.end_time - call.start_time).total_seconds()

    await session.commit()
    await session.refresh(call)
    return call


async def purge_old_transcripts(session: AsyncSession, retention_days: int = 30) -> int:
    """Enforces privacy retention policy by scrubbing transcripts older than retention_days."""
    cutoff = utc_now() - timedelta(days=retention_days)


    stmt = (
        update(Call)
        .where(Call.start_time < cutoff)
        .values(full_transcript="[PURGED_BY_RETENTION_POLICY]")
    )
    res = await session.execute(stmt)
    await session.commit()
    logger.info(f"Purged transcripts for {res.rowcount} calls older than {retention_days} days.")
    return res.rowcount
