"""Linear interpolation audio resampler converting arbitrary sample rates to 16 kHz PCM16 mono."""

import struct
from typing import List


def resample_pcm16_to_16k(pcm_bytes: bytes, source_rate: int) -> bytes:
    """Resamples linear 16-bit PCM audio from source_rate to 16,000 Hz mono.

    Uses continuous linear interpolation across sample boundaries.
    """
    if source_rate == 16000:
        return pcm_bytes

    sample_count = len(pcm_bytes) // 2
    if sample_count < 2:
        return b""

    samples: List[int] = list(struct.unpack(f"<{sample_count}h", pcm_bytes))
    ratio = source_rate / 16000.0
    out_samples: List[int] = []

    pos = 0.0
    while pos < sample_count - 1:
        i0 = int(pos)
        i1 = i0 + 1
        frac = pos - i0
        val = samples[i0] * (1.0 - frac) + samples[i1] * frac
        clamped = max(-32768, min(32767, int(round(val))))
        out_samples.append(clamped)
        pos += ratio

    return struct.pack(f"<{len(out_samples)}h", *out_samples)
