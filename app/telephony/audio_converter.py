"""Audio transcoding module for G.711 mu-law and 16-bit linear PCM conversion.

Compatible with Python 3.11, 3.12, and 3.13 without relying on deprecated or removed audioop.
Uses ITU-T standard precomputed tables for fast microsecond-level execution.
"""

import struct
from typing import List

BIAS = 0x84  # 132
CLIP = 32635

# Precompute 256-entry lookup table for G.711 mu-law (8-bit) to linear 16-bit PCM
_MULAW_TO_LINEAR_TABLE: List[int] = []
for i in range(256):
    inv = ~i & 0xFF
    sign = inv & 0x80
    exponent = (inv >> 4) & 0x07
    mantissa = inv & 0x0F
    sample = ((mantissa << 3) + BIAS) << exponent
    sample -= BIAS
    if sign != 0:
        sample = -sample
    _MULAW_TO_LINEAR_TABLE.append(sample)


def mulaw_to_linear(mulaw_bytes: bytes) -> bytes:
    """Decodes 8-bit G.711 mu-law audio bytes into 16-bit signed linear PCM (little-endian)."""
    samples = [_MULAW_TO_LINEAR_TABLE[b] for b in mulaw_bytes]
    return struct.pack(f"<{len(samples)}h", *samples)


def linear_to_mulaw(pcm_bytes: bytes) -> bytes:
    """Encodes 16-bit signed linear PCM bytes (little-endian) into 8-bit G.711 mu-law."""
    sample_count = len(pcm_bytes) // 2
    samples = struct.unpack(f"<{sample_count}h", pcm_bytes)
    result = bytearray(sample_count)

    for idx, sample in enumerate(samples):
        sign = 0x80 if sample < 0 else 0
        if sample < 0:
            sample = -sample
        if sample > CLIP:
            sample = CLIP

        sample += BIAS
        # Find exponent
        exponent = 7
        for exp in range(7):
            if sample <= (0x1F << (exp + 3)):
                exponent = exp
                break

        mantissa = (sample >> (exponent + 3)) & 0x0F
        mulaw_byte = ~(sign | (exponent << 4) | mantissa) & 0xFF
        result[idx] = mulaw_byte

    return bytes(result)


def create_silence_mulaw(duration_ms: int = 20, sample_rate: int = 8000) -> bytes:
    """Generates silent G.711 mu-law bytes for a given duration (default 20ms = 160 bytes)."""
    num_samples = int(sample_rate * (duration_ms / 1000.0))
    # 0xFF is standard quiet value in mu-law
    return b"\xff" * num_samples
