/**
 * AudioWorkletProcessor that resamples browser-native sample rates to 16 kHz
 * PCM16 mono, using the shared resampler module as the single source of truth.
 *
 * Loaded as a module worklet via: audioCtx.audioWorklet.addModule(url, { type: 'module' })
 * Module worklets can use static `import` for same-origin URLs.
 */

import { resampleFloat32ToPCM16 } from './resampler.js';

class PCMProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.targetRate = 16000;
    this.buffer = new Int16Array(320); // 20ms frame = 320 samples at 16kHz
    this.bufIndex = 0;
    this._residual = new Float32Array(0);
  }

  process(inputs, outputs, parameters) {
    const input = inputs[0];
    if (!input || !input[0]) return true;
    const channelData = input[0];

    // Concatenate any residual samples from the previous render quantum
    let samples;
    if (this._residual.length > 0) {
      samples = new Float32Array(this._residual.length + channelData.length);
      samples.set(this._residual);
      samples.set(channelData, this._residual.length);
      this._residual = new Float32Array(0);
    } else {
      samples = channelData;
    }

    // Resample using the shared algorithm
    const resampled = resampleFloat32ToPCM16(samples, sampleRate, this.targetRate);

    // Buffer into 320-sample (20ms) frames
    let srcIdx = 0;
    while (srcIdx < resampled.length) {
      const remaining = 320 - this.bufIndex;
      const available = resampled.length - srcIdx;
      const toCopy = Math.min(remaining, available);

      this.buffer.set(resampled.subarray(srcIdx, srcIdx + toCopy), this.bufIndex);
      this.bufIndex += toCopy;
      srcIdx += toCopy;

      if (this.bufIndex >= 320) {
        const chunk = this.buffer.slice(0, 320).buffer;
        this.port.postMessage(chunk, [chunk]);
        this.buffer = new Int16Array(320);
        this.bufIndex = 0;
      }
    }

    return true;
  }
}

registerProcessor('pcm-processor', PCMProcessor);
