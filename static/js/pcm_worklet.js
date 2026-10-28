/**
 * AudioWorkletProcessor that resamples browser-native sample rates to 16 kHz
 * PCM16 mono, using the shared StreamingResampler module as the single source of truth.
 *
 * Loaded as a module worklet via: audioCtx.audioWorklet.addModule(url)
 * Module worklets can use static `import` for same-origin URLs.
 */

import { StreamingResampler } from './resampler.js';

class PCMProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.targetRate = 16000;
    this.resampler = new StreamingResampler(sampleRate, this.targetRate);
    this.buffer = new Int16Array(320); // 20ms frame = 320 samples at 16kHz
    this.bufIndex = 0;
  }

  process(inputs, outputs, parameters) {
    const input = inputs[0];
    if (!input || !input[0]) return true;
    const channelData = input[0];

    // Resample block using the shared streaming resampler
    // (maintains fractional interpolation position and residual input samples across blocks)
    const resampled = this.resampler.process(channelData);

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
