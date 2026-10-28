/**
 * Pure JavaScript Audio Resampler for Linear 16-bit PCM.
 * Matches mathematical specification in app/transport/resampler.py
 */

function resamplePCM16(samples, sourceRate, targetRate = 16000) {
  if (sourceRate === targetRate) {
    return new Int16Array(samples);
  }
  const sampleCount = samples.length;
  if (sampleCount < 2) {
    return new Int16Array(0);
  }

  const ratio = sourceRate / targetRate;
  const outSamples = [];
  let pos = 0.0;

  while (pos < sampleCount - 1) {
    const i0 = Math.floor(pos);
    const i1 = i0 + 1;
    const frac = pos - i0;
    const val = samples[i0] * (1.0 - frac) + samples[i1] * frac;
    const clamped = Math.max(-32768, Math.min(32767, Math.round(val)));
    outSamples.push(clamped);
    pos += ratio;
  }

  return new Int16Array(outSamples);
}

function resampleFloat32ToPCM16(floatSamples, sourceRate, targetRate = 16000) {
  const int16Samples = new Int16Array(floatSamples.length);
  for (let i = 0; i < floatSamples.length; i++) {
    const clamped = Math.max(-1.0, Math.min(1.0, floatSamples[i]));
    int16Samples[i] = clamped < 0 ? Math.round(clamped * 32768) : Math.round(clamped * 32767);
  }
  return resamplePCM16(int16Samples, sourceRate, targetRate);
}

// ES module exports (used by AudioWorklet module import)
export { resamplePCM16, resampleFloat32ToPCM16 };

// CommonJS exports (used by Node.js tests)
if (typeof module !== "undefined" && module.exports) {
  module.exports = { resamplePCM16, resampleFloat32ToPCM16 };
}

