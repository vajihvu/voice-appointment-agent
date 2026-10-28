/**
 * AudioWorkletProcessor using pure linear resampling from static/js/resampler.js
 */

class PCMProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.targetRate = 16000;
    this.ratio = sampleRate / this.targetRate; // e.g. 48000/16000 = 3.0
    this.pos = 0.0;
    this.buffer = new Int16Array(320); // 20ms frame = 320 samples at 16kHz
    this.bufIndex = 0;
  }

  process(inputs, outputs, parameters) {
    const input = inputs[0];
    if (!input || !input[0]) return true;
    const channelData = input[0];
    const len = channelData.length;

    while (this.pos < len - 1) {
      const i0 = Math.floor(this.pos);
      const i1 = i0 + 1;
      const frac = this.pos - i0;

      // Linear interpolation between consecutive input samples
      const sample = channelData[i0] * (1.0 - frac) + channelData[i1] * frac;

      // Clamp and quantize Float32 [-1.0, 1.0] to signed Int16 [-32768, 32767]
      const clamped = Math.max(-1.0, Math.min(1.0, sample));
      this.buffer[this.bufIndex++] = clamped < 0 ? Math.round(clamped * 32768) : Math.round(clamped * 32767);

      if (this.bufIndex >= 320) {
        const chunk = this.buffer.slice(0, 320).buffer;
        this.port.postMessage(chunk, [chunk]);
        this.buffer = new Int16Array(320);
        this.bufIndex = 0;
      }

      this.pos += this.ratio;
    }

    this.pos -= len;
    return true;
  }
}

registerProcessor('pcm-processor', PCMProcessor);

