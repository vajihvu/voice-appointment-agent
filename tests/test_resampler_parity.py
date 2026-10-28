"""Parity tests verifying Python resampler against golden vectors."""

import json
import struct
from pathlib import Path

from app.transport.resampler import resample_pcm16_to_16k

GOLDEN_PATH = Path(__file__).parent / "golden_resampler_vectors.json"


def test_python_resampler_against_golden_vectors():
    with open(GOLDEN_PATH, "r", encoding="utf-8") as f:
        cases = json.load(f)

    for case_name, data in cases.items():
        source_rate = data["source_rate"]
        input_samples = data["input_samples"]
        expected_output = data["expected_output"]

        pcm_in = struct.pack(f"<{len(input_samples)}h", *input_samples)
        pcm_out = resample_pcm16_to_16k(pcm_in, source_rate)
        out_samples = list(struct.unpack(f"<{len(pcm_out) // 2}h", pcm_out))

        assert out_samples == expected_output, f"Mismatch in case {case_name}: {out_samples} != {expected_output}"

