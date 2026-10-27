"""Unit tests for G.711 mu-law audio conversion: reference vectors and round-trip bounds."""

import struct

from app.telephony.audio_converter import (
    create_silence_mulaw,
    linear_to_mulaw,
    mulaw_to_linear,
)


def test_silence_reference():
    """Verify standard mu-law quiet silence byte (0xFF) and duration sizing."""
    silence_20ms = create_silence_mulaw(duration_ms=20, sample_rate=8000)
    assert len(silence_20ms) == 160  # 8000 * 0.020 = 160 bytes
    assert silence_20ms == b"\xff" * 160

    # Decoded silence should be near zero (0 in G.711 standard decoding)
    decoded_pcm = mulaw_to_linear(b"\xff")
    sample_val = struct.unpack("<h", decoded_pcm)[0]
    assert abs(sample_val) == 0


def test_known_reference_vectors():
    """Test known ITU-T G.711 mu-law reference points."""
    # 0 -> 0xFF
    pcm_zero = struct.pack("<h", 0)
    mulaw_zero = linear_to_mulaw(pcm_zero)
    assert mulaw_zero == b"\xff"

    # Extreme positive (~32124) -> 0x80
    pcm_max_pos = struct.pack("<h", 32000)
    mulaw_pos = linear_to_mulaw(pcm_max_pos)
    assert mulaw_pos == b"\x80"

    # Extreme negative (~-32124) -> 0x00
    pcm_max_neg = struct.pack("<h", -32000)
    mulaw_neg = linear_to_mulaw(pcm_max_neg)
    assert mulaw_neg == b"\x00"


def test_round_trip_quantization_bounds():
    """Verify that linear -> mu-law -> linear reconstruction satisfies G.711 quantization error bounds."""
    # Test across representative dynamic range: quiet, mid, and loud
    test_samples = [0, 50, 100, 500, 1000, 4000, 10000, 20000, 30000, -50, -500, -4000, -20000]

    for original in test_samples:
        pcm = struct.pack("<h", original)
        encoded = linear_to_mulaw(pcm)
        decoded_pcm = mulaw_to_linear(encoded)
        reconstructed = struct.unpack("<h", decoded_pcm)[0]

        diff = abs(original - reconstructed)
        if abs(original) < 100:
            # Low amplitude has absolute step size bounded by ~8
            assert diff <= 8, f"Sample {original}: error {diff} exceeded small-signal bound"
        else:
            # High amplitude logarithmic quantization error is bounded within 5%
            relative_error = diff / abs(original)
            assert relative_error <= 0.05, f"Sample {original}: relative error {relative_error:.3f} > 5%"


def test_frame_size_preservation():
    """Verify 20ms frame conversion maintains correct sample counts."""
    # 20ms of 8000Hz 16-bit PCM = 160 samples = 320 bytes
    pcm_20ms = struct.pack("<160h", *([1000] * 160))
    mulaw_20ms = linear_to_mulaw(pcm_20ms)
    assert len(mulaw_20ms) == 160  # 1 byte per sample in mu-law

    reconstructed_pcm = mulaw_to_linear(mulaw_20ms)
    assert len(reconstructed_pcm) == 320  # 2 bytes per sample in linear PCM
