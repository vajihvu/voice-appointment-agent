"""Mock LLM provider supporting deterministic responses and tool calling for tests and simulation."""

import json
from datetime import date, timedelta
from typing import Any, AsyncGenerator, Dict, List, Optional

from app.llm.base import LLMMessage, LLMProvider, LLMResponseChunk


class MockLLMProvider(LLMProvider):
    """Deterministic LLM provider that recognizes keywords and triggers tools or canned replies."""

    def __init__(self, responses: Optional[Dict[str, str]] = None):
        self.responses = responses or {}

    async def chat_stream(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncGenerator[LLMResponseChunk, None]:
        # Find the last user message
        last_user_msg = next((m for m in reversed(messages) if m.role == "user"), None)
        user_text = (last_user_msg.content or "").lower() if last_user_msg else ""


        # Case 1: Post-tool execution response
        if messages[-1].role == "tool":
            tool_content = messages[-1].content or ""
            try:
                tool_data = json.loads(tool_content)
                if "available_slots" in tool_data:
                    slots = tool_data.get("available_slots", [])
                    if slots:
                        reply = f"We have slots available at {', '.join(slots[:2])}. Which would you prefer?"
                    else:
                        reply = "I'm sorry, we are fully booked for that day. Would another date work?"
                elif tool_data.get("status") == "success":
                    name = tool_data.get("name", "there")
                    dt = tool_data.get("date", "")
                    tm = tool_data.get("time", "")
                    reply = f"Great! Your appointment has been booked for {name} on {dt} at {tm}."
                elif tool_data.get("status") == "conflict":
                    reply = tool_data.get("message", "That slot is already booked. Could we try another time?")
                elif tool_data.get("status") == "transfer_initiated":
                    reply = "Connecting you to our clinic team right now. Please stay on the line."
                else:
                    reply = "I have processed your request. Is there anything else I can help with?"
            except Exception:
                reply = "Your request has been processed. How else can I assist you today?"

            yield LLMResponseChunk(delta_text=reply, is_first_token=True, is_complete=True)
            return

        # Case 2: Inbound user text asks to check slots
        if any(w in user_text for w in ["check", "slots", "availability", "available", "free", "tomorrow", "appointment"]):
            if "book" not in user_text:
                target_date = str(date.today() + timedelta(days=1))
                yield LLMResponseChunk(
                    is_first_token=True,
                    tool_calls=[
                        {
                            "id": "call_mock_check_slots",
                            "name": "check_slots",
                            "arguments": json.dumps({"date": target_date}),
                        }
                    ],
                    is_complete=True,
                )
                return

        # Case 3: Inbound user text asks to book
        if "book" in user_text or "confirm" in user_text:
            target_date = str(date.today() + timedelta(days=1))
            yield LLMResponseChunk(
                is_first_token=True,
                tool_calls=[
                    {
                        "id": "call_mock_book_appointment",
                        "name": "book_appointment",
                        "arguments": json.dumps({
                            "name": "Test Patient",
                            "phone": "+919876543210",
                            "date": target_date,
                            "slot": "10:00",
                            "service": "Routine Cleaning",
                        }),
                    }
                ],
                is_complete=True,
            )
            return

        # Case 4: Transfer request
        if any(w in user_text for w in ["human", "doctor", "emergency", "receptionist", "speak to someone"]):
            yield LLMResponseChunk(
                is_first_token=True,
                tool_calls=[
                    {
                        "id": "call_mock_transfer",
                        "name": "transfer_to_human",
                        "arguments": json.dumps({"reason": "Caller requested human assistance"}),
                    }
                ],
                is_complete=True,
            )
            return

        # Default natural conversational reply
        reply = "Hello! Welcome to BrightSmile Dental. Would you like to check available slots or book an appointment today?"
        yield LLMResponseChunk(delta_text=reply, is_first_token=True, is_complete=True)
