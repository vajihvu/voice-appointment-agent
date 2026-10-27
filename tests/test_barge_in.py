"""Unit tests for conversational barge-in filtering: word count, confidence, and debounce timing."""

import time
from unittest.mock import MagicMock

from app.agent.session import CallSession
from app.llm.mock_llm import MockLLMProvider
from app.stt.base import STTEvent
from app.tts.mock_tts import MockTTSProvider


def create_test_session():
    """Helper to instantiate an isolated CallSession for barge-in testing."""
    session = CallSession(
        call_id="test-barge-in",
        caller_phone="+919876543210",
        llm_provider=MockLLMProvider(),
        tts_provider=MockTTSProvider(),
        db_session_factory=MagicMock(),
    )
    # Ensure config values are set
    session.min_words_for_barge = 2
    session.min_confidence_for_barge = 0.70
    session.debounce_ms = 200
    return session


def test_barge_in_ignored_when_agent_not_speaking():
    """Verify barge-in returns False if the agent is not actively speaking."""
    session = create_test_session()
    session.is_agent_speaking = False

    event = STTEvent(text="stop please", is_final=False, confidence=0.95, words_count=2)
    assert session.evaluate_barge_in(event) is False


def test_barge_in_ignored_for_insufficient_word_count():
    """Verify single-word backchannels ('hmm', 'uh-huh', 'yeah') do not interrupt playback."""
    session = create_test_session()
    session.is_agent_speaking = True

    # Empty text
    event_empty = STTEvent(text="", is_final=False, confidence=0.99, words_count=0)
    assert session.evaluate_barge_in(event_empty) is False

    # Single word "hmm"
    event_one_word = STTEvent(text="hmm", is_final=False, confidence=0.99, words_count=1)
    assert session.evaluate_barge_in(event_one_word) is False


def test_barge_in_ignored_for_low_confidence():
    """Verify noisy background audio (<0.70 confidence) does not interrupt playback."""
    session = create_test_session()
    session.is_agent_speaking = True

    event_low_conf = STTEvent(text="wait stop", is_final=False, confidence=0.55, words_count=2)
    assert session.evaluate_barge_in(event_low_conf) is False


def test_barge_in_debounce_window_edge_cases():
    """Verify debounce window behavior: initial trigger primes debounce, subsequent event must exceed debounce_ms."""
    session = create_test_session()
    session.is_agent_speaking = True

    event = STTEvent(text="wait please", is_final=False, confidence=0.90, words_count=2)

    # First detection sets _last_speech_detect_time, returns False
    session._last_speech_detect_time = 0.0
    first_check = session.evaluate_barge_in(event)

    assert first_check is False
    assert session._last_speech_detect_time > 0.0

    # Second check within 50ms (< 200ms debounce threshold) returns False
    session._last_speech_detect_time = time.time() - 0.05  # 50ms ago
    assert session.evaluate_barge_in(event) is False

    # Third check after 250ms (>= 200ms debounce threshold) returns True!
    session._last_speech_detect_time = time.time() - 0.25  # 250ms ago
    assert session.evaluate_barge_in(event) is True
