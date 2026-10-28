"""Conversational call session managing the turn-by-turn state machine and latency metrics."""

import asyncio
import json
import time
from datetime import date
from typing import Any, Callable, Coroutine, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import logger
from app.db.repository import finalize_call, log_turn_latency
from app.llm.base import LLMMessage, LLMProvider
from app.llm.tools import execute_tool, get_tool_definitions
from app.stt.base import STTEvent
from app.transport.base import VoiceTransport
from app.tts.base import TTSProvider

settings = get_settings()


class CallSession:
    """Manages conversational dialogue state, tool execution, and latency metrics for one call."""

    def __init__(
        self,
        call_id: str,
        caller_phone: str,
        llm_provider: LLMProvider,
        tts_provider: TTSProvider,
        db_session_factory: Callable[[], AsyncSession],
        transport: Optional[VoiceTransport] = None,
        send_audio_callback: Optional[Callable[[bytes], Coroutine[Any, Any, None]]] = None,
        clear_audio_callback: Optional[Callable[[], Coroutine[Any, Any, None]]] = None,
        language: str = "en",
    ):
        self.call_id = call_id
        self.caller_phone = caller_phone
        self.llm = llm_provider
        self.tts = tts_provider
        self.db_session_factory = db_session_factory
        self.transport = transport
        self.send_audio_callback = (transport.send_audio if transport else None) or send_audio_callback
        self.clear_audio_callback = (transport.clear_audio if transport else None) or clear_audio_callback
        self.language = language

        # Session State
        self.is_active = True
        self.is_agent_speaking = False
        self.turn_index = 0
        self.outcome = "inquiry"
        self.handoff_reason: Optional[str] = None
        self.full_transcript: List[Dict[str, str]] = []
        self.sms_sent = False

        # Barge-in configuration
        barge_cfg = settings.barge_in or {}
        self.barge_in_enabled = barge_cfg.get("enabled", True)
        self.min_words_for_barge = barge_cfg.get("min_words", 2)
        self.min_confidence_for_barge = barge_cfg.get("min_confidence", 0.70)
        self.debounce_ms = barge_cfg.get("debounce_ms", 200)
        self._last_speech_detect_time = 0.0
        self._current_playback_task: Optional[asyncio.Task] = None

        # Build initial system prompt
        self.messages: List[LLMMessage] = []
        self._init_system_prompt()

    def _init_system_prompt(self) -> None:
        """Injects business details and current date into the system prompt."""
        prompts = settings.prompts.get("languages", {}).get(self.language, {})
        system_tmpl = prompts.get("system_prompt", "You are a helpful phone receptionist.")
        formatted_prompt = system_tmpl.format(
            business_name=settings.business.get("name", "BrightSmile Dental"),
            business_type=settings.business.get("type", "dental clinic"),
            current_date=str(date.today()),
        )
        self.messages.append(LLMMessage(role="system", content=formatted_prompt))

    def evaluate_barge_in(self, event: STTEvent) -> bool:
        """Evaluates whether an interim or final STT event qualifies for barging in.

        Rules:
        - Only if agent is currently speaking.
        - Word count must exceed min_words or confidence >= min_confidence.
        - Speech must persist longer than debounce_ms to eliminate short backchannels like 'hmm'.
        """
        if not self.is_agent_speaking or not self.barge_in_enabled:
            return False

        now = time.time()
        words = event.text.strip().split()
        if len(words) < self.min_words_for_barge:
            return False
        if event.confidence < self.min_confidence_for_barge:
            return False

        # Debounce check
        if self._last_speech_detect_time == 0.0:
            self._last_speech_detect_time = now
            return False

        if (now - self._last_speech_detect_time) * 1000.0 < self.debounce_ms:
            return False

        return True

    async def trigger_barge_in(self) -> None:
        """Halts active agent audio playback immediately."""
        logger.info(f"Barge-in triggered on call {self.call_id}. Stopping playback.")
        self.is_agent_speaking = False
        self._last_speech_detect_time = 0.0

        if self._current_playback_task and not self._current_playback_task.done():
            self._current_playback_task.cancel()

        if self.clear_audio_callback:
            try:
                await self.clear_audio_callback()
            except Exception as e:
                logger.error(f"Error calling clear_audio_callback: {e}")

    async def process_caller_turn(
        self,
        transcript: str,
        speech_end_timestamp: Optional[float] = None,
        stt_latency_ms: float = 0.0,
    ) -> str:
        """Executes a complete conversational turn upon caller utterance completion.

        Latency Definition:
        `End of caller speech -> First agent audio byte sent over the WebSocket`
        (Server turn processing latency; excludes browser audio scheduling and network delay).
        """
        t_speech_end = speech_end_timestamp or time.time()
        self.turn_index += 1
        logger.info(f"Turn {self.turn_index} | Caller: '{transcript}'")
        self.full_transcript.append({"role": "caller", "content": transcript})
        self.messages.append(LLMMessage(role="user", content=transcript))

        if self.transport:
            try:
                await self.transport.send_event("transcript", {"role": "caller", "text": transcript})
                await self.transport.send_event("state", {"state": "thinking"})
            except Exception:
                pass

        t_llm_start = time.time()
        tool_called_name: Optional[str] = None
        assistant_reply = ""
        first_audio_byte_sent = False
        t_first_audio_byte: Optional[float] = None

        async with self.db_session_factory() as db:
            # 1. Query LLM (with tool definitions)
            tools = get_tool_definitions()
            llm_stream = self.llm.chat_stream(self.messages, tools=tools)

            accumulated_tool_calls: List[Dict[str, Any]] = []
            reply_chunks: List[str] = []

            async for chunk in llm_stream:
                if chunk.tool_calls:
                    accumulated_tool_calls.extend(chunk.tool_calls)
                if chunk.delta_text:
                    reply_chunks.append(chunk.delta_text)

            t_llm_done = time.time()
            llm_latency_ms = (t_llm_done - t_llm_start) * 1000.0

            # 2. Check if tools were invoked
            if accumulated_tool_calls:
                # Add assistant message with tool calls to history
                self.messages.append(
                    LLMMessage(
                        role="assistant",
                        content=None,
                        tool_calls=accumulated_tool_calls,
                    )
                )

                for tc in accumulated_tool_calls:
                    func_name = tc.get("name")
                    func_args = tc.get("arguments", "{}")
                    tool_called_name = func_name

                    # Execute the tool
                    tool_res = await execute_tool(
                        db_session=db,
                        tool_name=func_name,
                        arguments_json=func_args,
                        call_id=self.call_id,
                        caller_phone=self.caller_phone,
                    )

                    # Update session outcomes
                    if func_name == "book_appointment" and tool_res.get("status") == "success":
                        self.outcome = "booked"
                    elif func_name == "cancel_appointment" and tool_res.get("status") == "success":
                        self.outcome = "cancelled"
                    elif func_name == "transfer_to_human":
                        self.outcome = "human_handoff"
                        self.handoff_reason = tool_res.get("reason")
                    elif func_name == "send_confirmation_sms":
                        self.sms_sent = True

                    # Add tool response to history
                    self.messages.append(
                        LLMMessage(
                            role="tool",
                            content=json.dumps(tool_res),
                            tool_call_id=tc.get("id"),
                            name=func_name,
                        )
                    )

                # Re-query LLM for the final conversational reply after tool execution
                post_tool_stream = self.llm.chat_stream(self.messages)
                reply_chunks = []
                async for chunk in post_tool_stream:
                    if chunk.delta_text:
                        reply_chunks.append(chunk.delta_text)

            assistant_reply = "".join(reply_chunks).strip()
            self.messages.append(LLMMessage(role="assistant", content=assistant_reply))
            self.full_transcript.append({"role": "agent", "content": assistant_reply})
            logger.info(f"Turn {self.turn_index} | Agent: '{assistant_reply}'")

            if self.transport:
                try:
                    await self.transport.send_event("transcript", {"role": "agent", "text": assistant_reply})
                    await self.transport.send_event("state", {"state": "speaking"})
                except Exception:
                    pass

            # 3. Stream TTS synthesis & measure mouth-to-ear latency
            t_tts_start = time.time()
            self.is_agent_speaking = True

            async def stream_audio_out() -> None:
                nonlocal first_audio_byte_sent, t_first_audio_byte
                tts_chunks = self.tts.synthesize_text(assistant_reply)
                async for chunk in tts_chunks:
                    if not self.is_agent_speaking:
                        break  # Interrupted by barge-in
                    if not first_audio_byte_sent:
                        t_first_audio_byte = time.time()
                        first_audio_byte_sent = True
                    if self.send_audio_callback:
                        await self.send_audio_callback(chunk.audio_bytes)
                self.is_agent_speaking = False
                if self.transport:
                    try:
                        await self.transport.send_event("state", {"state": "listening"})
                    except Exception:
                        pass

            self._current_playback_task = asyncio.create_task(stream_audio_out())
            try:
                await self._current_playback_task
            except asyncio.CancelledError:
                logger.info("Playback task was cancelled via barge-in.")

            # 4. Compute strict latency: end of speech -> first audio byte sent
            if t_first_audio_byte:
                total_turn_latency_ms = (t_first_audio_byte - t_speech_end) * 1000.0
                tts_latency_ms = (t_first_audio_byte - t_tts_start) * 1000.0
            else:
                total_turn_latency_ms = (time.time() - t_speech_end) * 1000.0
                tts_latency_ms = 0.0

            # Log latency metrics to database
            await log_turn_latency(
                session=db,
                call_id=self.call_id,
                turn_index=self.turn_index,
                speaker="caller",
                user_transcript=transcript,
                agent_response=assistant_reply,
                tool_called=tool_called_name,
                stt_latency_ms=stt_latency_ms,
                llm_latency_ms=llm_latency_ms,
                tts_latency_ms=tts_latency_ms,
                total_turn_latency_ms=total_turn_latency_ms,
            )

        return assistant_reply

    async def end_call(self) -> None:
        """Finalizes the call in the database."""
        self.is_active = False
        async with self.db_session_factory() as db:
            await finalize_call(
                session=db,
                call_id=self.call_id,
                status="transferred" if self.outcome == "human_handoff" else "completed",
                outcome=self.outcome,
                handoff_reason=self.handoff_reason,
                full_transcript=json.dumps(self.full_transcript),
                sms_sent=self.sms_sent,
            )
        logger.info(f"Call {self.call_id} closed with outcome '{self.outcome}'.")
