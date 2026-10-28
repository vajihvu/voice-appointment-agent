/**
 * Pure JavaScript Audio Resampler for Linear 16-bit PCM.
 * Matches mathematical specification in app/transport/resampler.py
 */

class StreamingResampler {
  constructor(sourceRate, targetRate = 16000) {
    this.sourceRate = sourceRate;
    this.targetRate = targetRate;
    this.ratio = sourceRate / targetRate;
    this.pos = 0.0;
    this.residual = new Float32Array(0);
  }

  process(channelData) {
    if (this.sourceRate === this.targetRate) {
      const int16Samples = new Int16Array(channelData.length);
      for (let i = 0; i < channelData.length; i++) {
        const clamped = Math.max(-1.0, Math.min(1.0, channelData[i]));
        int16Samples[i] = clamped < 0 ? Math.round(clamped * 32768) : Math.round(clamped * 32767);
      }
      return int16Samples;
    }

    let samples;
    if (this.residual.length > 0) {
      samples = new Float32Array(this.residual.length + channelData.length);
      samples.set(this.residual);
      samples.set(channelData, this.residual.length);
    } else {
      samples = channelData;
    }

    const totalLength = samples.length;
    if (totalLength < 2) {
      this.residual = samples;
      return new Int16Array(0);
    }

    const outSamples = [];
    while (this.pos < totalLength - 1) {
      const i0 = Math.floor(this.pos);
      const i1 = i0 + 1;
      const frac = this.pos - i0;
      const sample = samples[i0] * (1.0 - frac) + samples[i1] * frac;
      const clamped = Math.max(-1.0, Math.min(1.0, sample));
      outSamples.push(clamped < 0 ? Math.round(clamped * 32768) : Math.round(clamped * 32767));
      this.pos += this.ratio;
    }

    const lastNeededIdx = Math.floor(this.pos);
    if (lastNeededIdx < totalLength) {
      this.residual = samples.slice(lastNeededIdx);
      this.pos -= lastNeededIdx;
    } else {
      this.residual = new Float32Array(0);
      this.pos -= totalLength;
    }

    return new Int16Array(outSamples);
  }
}

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
  return new StreamingResampler(sourceRate, targetRate).process(floatSamples);
}

// ES module exports (used by AudioWorklet module import)
export { StreamingResampler, resamplePCM16, resampleFloat32ToPCM16 };

// CommonJS exports (guarded for Node.js environments; cannot throw ReferenceError in browser worklets)
if (typeof module !== "undefined" && typeof module.exports !== "undefined") {
  module.exports = { StreamingResampler, resamplePCM16, resampleFloat32ToPCM16 };
}
