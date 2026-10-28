"""Unit tests for audio resampling from native browser rates (48kHz, 44.1kHz) to 16kHz PCM16."""

import math
import struct

from app.transport.resampler import resample_pcm16_to_16k


def test_resample_identity_at_16k():
    """Verify resampling from 16kHz to 16kHz is an exact no-op."""
    pcm = struct.pack("<5h", 100, 200, -300, 400, 0)
    assert resample_pcm16_to_16k(pcm, 16000) == pcm


def test_resample_from_48k_to_16k_ratio():
    """Verify 48kHz audio resamples to exactly 1/3 sample count."""
    # 480 samples at 48kHz = 10ms
    # 10ms at 16kHz = 160 samples
    samples_48k = [int(10000 * math.sin(2 * math.pi * 440 * i / 48000)) for i in range(480)]
    pcm_48k = struct.pack(f"<{len(samples_48k)}h", *samples_48k)

    resampled = resample_pcm16_to_16k(pcm_48k, 48000)
    out_samples = struct.unpack(f"<{len(resampled)//2}h", resampled)

    # Ratio 48000 / 16000 = 3.0. 480 samples -> 160 samples (or within 1 sample edge boundary)
    assert abs(len(out_samples) - 160) <= 1
    # Verify amplitude bounds preserved without clipping distortion
    assert max(out_samples) > 8000
    assert min(out_samples) < -8000


def test_resample_from_44k1_to_16k():
    """Verify 44.1kHz audio downsamples without numeric error or overflow."""
    # 441 samples at 44.1kHz = 10ms
    # 10ms at 16kHz = 160 samples
    samples_44k = [int(5000 * math.sin(2 * math.pi * 1000 * i / 44100)) for i in range(441)]
    pcm_44k = struct.pack(f"<{len(samples_44k)}h", *samples_44k)

    resampled = resample_pcm16_to_16k(pcm_44k, 44100)
    out_samples = struct.unpack(f"<{len(resampled)//2}h", resampled)

    # 441 / (44100/16000) = 160 samples
    assert abs(len(out_samples) - 160) <= 1
