import argparse
import asyncio
import sys
import time
import uuid
import wave
from pathlib import Path
from typing import List

# Ensure project root is on sys.path for direct CLI invocation
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agent.session import CallSession
from app.core.config import get_settings
from app.core.logging import logger, mask_phone_number
from app.db.connection import AsyncSessionLocal, init_db
from app.db.repository import create_or_get_call
from app.llm.mock_llm import MockLLMProvider
from app.tts.mock_tts import MockTTSProvider

settings = get_settings()


if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


class LocalCallSimulator:
    """Simulates inbound call sessions locally, feeding text or WAV audio into the pipeline."""

    def __init__(
        self,
        caller_phone: str = "+919876543210",
        llm_provider=None,
        tts_provider=None,
        db_session_factory=None,
    ):
        self.caller_phone = caller_phone
        self.llm_provider = llm_provider or MockLLMProvider()
        self.tts_provider = tts_provider or MockTTSProvider()
        self.db_session_factory = db_session_factory or AsyncSessionLocal
        self.received_audio_bytes = 0

    async def _send_audio_callback(self, audio_chunk: bytes) -> None:
        """Simulates sending audio back to the client transport."""
        self.received_audio_bytes += len(audio_chunk)

    async def _clear_audio_callback(self) -> None:
        """Simulates sending clearAudio to the client transport (barge-in interruption)."""
        logger.info("[Simulator] Received clearAudio signal (barge-in interruption).")

    async def run_dialogue(self, turns: List[str]) -> CallSession:
        """Executes a scripted sequence of turns against the agent."""
        await init_db()
        call_uuid = f"sim-{uuid.uuid4().hex[:12]}"

        async with self.db_session_factory() as db:
            call_record = await create_or_get_call(
                session=db,
                caller_phone=self.caller_phone,
                external_call_id=call_uuid,
            )
            call_id = call_record.id

        session = CallSession(
            call_id=call_id,
            caller_phone=self.caller_phone,
            llm_provider=self.llm_provider,
            tts_provider=self.tts_provider,
            db_session_factory=self.db_session_factory,
            send_audio_callback=self._send_audio_callback,
            clear_audio_callback=self._clear_audio_callback,
        )

        print("\n" + "=" * 60)
        print(f"[CALL SIMULATOR STARTED] ID: {call_id}")
        print(f"Caller Phone: {mask_phone_number(self.caller_phone)}")
        print("=" * 60 + "\n")

        for turn_text in turns:
            print(f"[CALLER]: {turn_text}")
            t_speech_end = time.time()
            reply = await session.process_caller_turn(
                transcript=turn_text,
                speech_end_timestamp=t_speech_end,
                stt_latency_ms=150.0,
            )
            print(f"[AGENT] : {reply}\n")

        await session.end_call()
        print("=" * 60)
        print(f"[CALL TERMINATED] Final Outcome: '{session.outcome}'")
        print(f"Total Synthesized Audio Packets: {self.received_audio_bytes} bytes")
        print("=" * 60 + "\n")
        return session

    async def run_wav_file(self, wav_path: Path) -> None:
        """Simulates processing a WAV file, chunking it into 20ms frames."""
        if not wav_path.exists():
            print(f"Error: WAV file {wav_path} not found.")
            return

        with wave.open(str(wav_path), "rb") as wf:
            n_channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            framerate = wf.getframerate()

        print(f"Processing WAV: {wav_path.name} | {framerate}Hz, {n_channels}ch, {sampwidth}B/sample")
        await self.run_dialogue(["Hi, I want to book an appointment for dental cleaning tomorrow."])


async def interactive_shell():
    """Runs an interactive command-line simulator session."""
    sim = LocalCallSimulator()
    await init_db()
    call_uuid = f"sim-{uuid.uuid4().hex[:12]}"

    async with AsyncSessionLocal() as db:
        call = await create_or_get_call(
            session=db,
            caller_phone="+919876543210",
            external_call_id=call_uuid,
        )
        call_id = call.id

    session = CallSession(
        call_id=call_id,
        caller_phone="+919876543210",
        llm_provider=MockLLMProvider(),
        tts_provider=MockTTSProvider(),
        db_session_factory=AsyncSessionLocal,
        send_audio_callback=sim._send_audio_callback,
        clear_audio_callback=sim._clear_audio_callback,
    )

    print("\n" + "=" * 65)
    print("[INTERACTIVE VOICE APPOINTMENT SIMULATOR]")
    print("Type your message and press ENTER. Type 'exit' or 'quit' to end call.")
    print("=" * 65 + "\n")

    while True:
        try:
            user_input = input("[YOU]: ").strip()
            if not user_input:
                continue
            if user_input.lower() in ["exit", "quit", "hangup"]:
                break

            t_speech_end = time.time()
            reply = await session.process_caller_turn(
                transcript=user_input,
                speech_end_timestamp=t_speech_end,
                stt_latency_ms=120.0,
            )
            print(f"[AGENT]: {reply}\n")
        except (KeyboardInterrupt, EOFError):
            break

    await session.end_call()
    print(f"\nCall ended. Final outcome recorded in SQLite DB: {session.outcome}\n")



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Voice Appointment Agent Local Simulator")
    parser.add_argument("--interactive", action="store_true", help="Launch interactive CLI conversation")
    parser.add_argument("--wav", type=str, help="Path to WAV audio file to feed through pipeline")
    args = parser.parse_args()

    if args.interactive:
        asyncio.run(interactive_shell())
    elif args.wav:
        sim = LocalCallSimulator()
        asyncio.run(sim.run_wav_file(Path(args.wav)))
    else:
        # Default test dialogue
        sim = LocalCallSimulator()
        asyncio.run(
            sim.run_dialogue([
                "Hi, what appointment slots do you have tomorrow?",
                "Please book 10:00 AM for Alice for dental cleaning.",
                "Thank you!",
            ])
        )
