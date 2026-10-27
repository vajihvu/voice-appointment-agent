"""LLM tool definitions, JSON schemas, and execution dispatcher."""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import logger, mask_phone_number
from app.db.repository import (
    SlotAlreadyBookedException,
    book_appointment_tx,
    cancel_appointment_tx,
    get_available_slots,
)

settings = get_settings()


def get_tool_definitions() -> List[Dict[str, Any]]:
    """Returns OpenAI-compatible JSON schemas for all available phone agent tools."""
    return [
        {
            "type": "function",
            "function": {
                "name": "check_slots",
                "description": "Checks available appointment slots for a specific date at the clinic. Always call this when a caller inquires about availability.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "date": {
                            "type": "string",
                            "description": "The date in YYYY-MM-DD format (e.g. '2026-10-29').",
                        }
                    },
                    "required": ["date"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "book_appointment",
                "description": "Books an appointment slot for the patient. You must have the patient's name, phone number, date, and slot time before calling this.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Full name of the patient/caller.",
                        },
                        "phone": {
                            "type": "string",
                            "description": "Caller's contact phone number in E.164 format (e.g. +919876543210).",
                        },
                        "date": {
                            "type": "string",
                            "description": "Date of appointment in YYYY-MM-DD format.",
                        },
                        "slot": {
                            "type": "string",
                            "description": "Start time of the slot (e.g., '10:00' or '14:30').",
                        },
                        "service": {
                            "type": "string",
                            "description": "The requested service (e.g., 'Routine Cleaning', 'General Consultation', 'Teeth Whitening'). Defaults to 'General Consultation'.",
                        },
                    },
                    "required": ["name", "phone", "date", "slot"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "cancel_appointment",
                "description": "Cancels an existing appointment given the appointment ID.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "appointment_id": {
                            "type": "string",
                            "description": "The unique UUID of the appointment to cancel.",
                        }
                    },
                    "required": ["appointment_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "transfer_to_human",
                "description": "Transfers the phone call to a human receptionist or doctor. Use when requested by the caller, in emergencies, or when unresolvable issues occur.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "reason": {
                            "type": "string",
                            "description": "Brief explanation of why the call is being handed off to a human.",
                        }
                    },
                    "required": ["reason"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "send_confirmation_sms",
                "description": "Sends an SMS booking confirmation to the caller's phone number.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "phone": {
                            "type": "string",
                            "description": "Recipient phone number.",
                        },
                        "appointment_id": {
                            "type": "string",
                            "description": "The booked appointment ID.",
                        },
                    },
                    "required": ["phone"],
                },
            },
        },
    ]


async def execute_tool(
    db_session: AsyncSession,
    tool_name: str,
    arguments_json: str,
    call_id: Optional[str] = None,
    caller_phone: Optional[str] = None,
) -> Dict[str, Any]:
    """Executes the requested tool and returns structured result."""
    try:
        args = json.loads(arguments_json) if isinstance(arguments_json, str) else arguments_json
    except Exception as e:
        logger.error(f"Failed to parse tool arguments: {e}")
        return {"error": "Invalid arguments JSON format"}

    logger.info(f"Executing tool '{tool_name}' with args: {args}")

    if tool_name == "check_slots":
        date_str = args.get("date")
        if not date_str:
            return {"error": "Date parameter is required in YYYY-MM-DD format."}
        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return {"error": f"Invalid date format '{date_str}'. Please use YYYY-MM-DD."}

        slots = await get_available_slots(db_session, target_date)
        if not slots:
            return {
                "date": date_str,
                "available_slots": [],
                "message": f"Sorry, all slots are fully booked for {date_str}. Please suggest another date.",
            }
        # Return top 4 slots to avoid overwhelming the caller
        return {
            "date": date_str,
            "available_slots": slots,
            "recommended_slots": slots[:3],
            "total_available": len(slots),
        }

    elif tool_name == "book_appointment":
        name = args.get("name")
        phone = args.get("phone") or caller_phone
        date_str = args.get("date")
        slot_str = args.get("slot")
        service = args.get("service", "General Consultation")

        if not all([name, phone, date_str, slot_str]):
            return {"error": "Missing required fields: name, phone, date, or slot."}

        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return {"error": f"Invalid date format '{date_str}'. Expected YYYY-MM-DD."}

        # Normalize slot time format (e.g. "10:00 AM" -> "10:00")
        normalized_slot = slot_str.split()[0].zfill(5) if ":" in slot_str else slot_str

        try:
            appointment = await book_appointment_tx(
                session=db_session,
                customer_name=name,
                customer_phone=phone,
                appointment_date=target_date,
                start_time=normalized_slot,
                service_type=service,
                call_id=call_id,
            )
            return {
                "status": "success",
                "appointment_id": appointment.id,
                "name": appointment.customer_name,
                "date": str(appointment.appointment_date),
                "time": appointment.start_time,
                "service": appointment.service_type,
                "message": f"Appointment successfully confirmed for {appointment.customer_name} on {appointment.appointment_date} at {appointment.start_time}.",
            }
        except SlotAlreadyBookedException as e:
            try:
                alternative_slots = await get_available_slots(db_session, target_date)
            except Exception:
                alternative_slots = []
            alt_msg = f" The next available slots on {date_str} are {', '.join(alternative_slots[:3])}." if alternative_slots else ""
            return {
                "status": "conflict",
                "error": str(e),
                "message": f"Unfortunately that slot is already taken.{alt_msg}",
                "alternative_slots": alternative_slots[:3],
            }

        except Exception as e:
            logger.error(f"Error booking appointment: {e}")
            return {"status": "error", "message": f"Failed to complete booking: {str(e)}"}

    elif tool_name == "cancel_appointment":
        appointment_id = args.get("appointment_id")
        if not appointment_id:
            return {"error": "appointment_id is required."}
        success = await cancel_appointment_tx(db_session, appointment_id)
        if success:
            return {"status": "success", "message": f"Appointment {appointment_id} has been cancelled."}
        return {"status": "not_found", "message": "Appointment not found or already cancelled."}

    elif tool_name == "transfer_to_human":
        reason = args.get("reason", "Caller requested a human agent.")
        logger.info(f"Transfer to human triggered: {reason}")
        return {
            "status": "transfer_initiated",
            "destination_number": settings.HUMAN_HANDOFF_NUMBER,
            "reason": reason,
            "message": "Initiating handoff to human staff.",
        }

    elif tool_name == "send_confirmation_sms":
        phone = args.get("phone") or caller_phone
        appointment_id = args.get("appointment_id", "APP-CONFIRMED")
        # In Phase 1, logs confirmation dispatch; integrated with Plivo SMS in Phase 4
        logger.info(f"SMS confirmation queued for {mask_phone_number(phone)} (Ref: {appointment_id})")
        return {
            "status": "queued",
            "phone": mask_phone_number(phone),
            "message": "Confirmation SMS has been queued.",
        }

    return {"error": f"Unknown tool: {tool_name}"}
