"""SQLAlchemy declarative models for calls, latencies, appointments, and schedule slots."""

import uuid
from datetime import date, datetime, timezone
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    """Returns a timezone-naive UTC datetime for SQLite compatibility."""
    return datetime.now(timezone.utc).replace(tzinfo=None)



class Base(DeclarativeBase):
    pass


class Call(Base):
    """Represents a phone call session received via Plivo."""

    __tablename__ = "calls"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    plivo_call_uuid: Mapped[Optional[str]] = mapped_column(String(64), unique=True, index=True, nullable=True)
    caller_phone: Mapped[str] = mapped_column(String(32), index=True)
    start_time: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    end_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="in_progress")  # in_progress, completed, failed, transferred
    outcome: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # booked, inquiry, cancelled, human_handoff
    handoff_reason: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    total_duration_sec: Mapped[Optional[float]] = mapped_column(Float, default=0.0)
    full_transcript: Mapped[Optional[str]] = mapped_column(Text, default="")
    sms_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    # Relationships
    latencies: Mapped[List["TurnLatency"]] = relationship("TurnLatency", back_populates="call", cascade="all, delete-orphan")
    appointments: Mapped[List["Appointment"]] = relationship("Appointment", back_populates="call")


class TurnLatency(Base):
    """Records performance and latency measurements for each conversational turn."""

    __tablename__ = "turn_latencies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    call_id: Mapped[str] = mapped_column(String(36), ForeignKey("calls.id", ondelete="CASCADE"), index=True)
    turn_index: Mapped[int] = mapped_column(Integer)
    speaker: Mapped[str] = mapped_column(String(16), default="caller")
    user_transcript: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    agent_response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tool_called: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Latencies in milliseconds
    stt_latency_ms: Mapped[Optional[float]] = mapped_column(Float, default=0.0)
    llm_latency_ms: Mapped[Optional[float]] = mapped_column(Float, default=0.0)
    tts_latency_ms: Mapped[Optional[float]] = mapped_column(Float, default=0.0)
    total_turn_latency_ms: Mapped[Optional[float]] = mapped_column(Float, default=0.0)  # end of speech -> first audio byte

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


    call: Mapped["Call"] = relationship("Call", back_populates="latencies")


class Appointment(Base):
    """Booked appointment record with unique constraint to prevent double-booking."""

    __tablename__ = "appointments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    call_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("calls.id"), nullable=True)
    customer_name: Mapped[str] = mapped_column(String(128))
    customer_phone: Mapped[str] = mapped_column(String(32), index=True)
    appointment_date: Mapped[date] = mapped_column(Date, index=True)
    start_time: Mapped[str] = mapped_column(String(16))  # e.g., "10:00 AM" or "10:00"
    end_time: Mapped[str] = mapped_column(String(16))    # e.g., "10:30 AM" or "10:30"
    service_type: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="confirmed")  # confirmed, cancelled, rescheduled
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


    call: Mapped[Optional["Call"]] = relationship("Call", back_populates="appointments")

    __table_args__ = (
        # Ensure that no two active appointments share the same date and start time
        UniqueConstraint("appointment_date", "start_time", name="uq_appointment_slot"),
    )


class ScheduleSlot(Base):
    """Specific bookable clinic calendar slot."""

    __tablename__ = "schedule_slots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slot_date: Mapped[date] = mapped_column(Date, index=True)
    start_time: Mapped[str] = mapped_column(String(16))  # e.g., "10:00"
    end_time: Mapped[str] = mapped_column(String(16))    # e.g., "10:30"
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    booked_by_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    booked_by_phone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    appointment_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("appointments.id"), nullable=True)

    __table_args__ = (
        UniqueConstraint("slot_date", "start_time", name="uq_schedule_slot"),
    )
