"""Notifier interface and DatabaseNotifier implementation for appointment confirmations."""

from abc import ABC, abstractmethod
from typing import Optional

from app.core.logging import logger, mask_phone_number
from app.db.connection import AsyncSessionLocal
from app.db.repository import create_notification


class Notifier(ABC):
    """Abstract notification service interface."""

    @abstractmethod
    async def send_confirmation(
        self,
        recipient: str,
        message: str,
        appointment_id: Optional[str] = None,
        call_id: Optional[str] = None,
    ) -> bool:
        """Dispatches an appointment confirmation or update notification."""
        pass


class DatabaseNotifier(Notifier):
    """Default notifier that persists confirmation messages into the SQLite database.

    Requires no external services or paid SMS credits, and makes confirmations
    instantly visible in the management dashboard and call logs.
    """

    async def send_confirmation(
        self,
        recipient: str,
        message: str,
        appointment_id: Optional[str] = None,
        call_id: Optional[str] = None,
    ) -> bool:
        try:
            async with AsyncSessionLocal() as session:
                await create_notification(
                    session=session,
                    recipient=recipient,
                    message=message,
                    appointment_id=appointment_id,
                    call_id=call_id,
                    status="recorded",
                )
            logger.info(
                f"[NOTIFICATION RECORDED] Recipient: {mask_phone_number(recipient)} | "
                f"Appointment: {appointment_id or 'N/A'} | Text: '{message}'"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to record confirmation notification in database: {e}")
            return False
