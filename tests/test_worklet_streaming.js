/**
 * Node.js test verifying streaming block-by-block resampling in PCMProcessor
 * against one-shot resampleFloat32ToPCM16 on identical continuous signals.
 */

const fs = require('fs');
const path = require('path');

async function runStreamingTest() {
  let passed = true;
  const sampleRates = [48000, 44100];

  for (const sr of sampleRates) {
    globalThis.AudioWorkletProcessor = class AudioWorkletProcessor {};
    globalThis.registerProcessor = (name, cls) => { globalThis.__PCMProcessor = cls; };
    globalThis.sampleRate = sr;

    // Load worklet dynamically
    const workletPath = path.resolve(__dirname, '../static/js/pcm_worklet.js');
    await import('file:///' + workletPath.replace(/\\/g, '/') + '?sr=' + sr + '&t=' + Date.now());
    const PCMProcessor = globalThis.__PCMProcessor;

    const resamplerPath = path.resolve(__dirname, '../static/js/resampler.js');
    const { resampleFloat32ToPCM16 } = await import('file:///' + resamplerPath.replace(/\\/g, '/') + '?t=' + Date.now());

    const proc = new PCMProcessor();
    const postedChunks = [];
    proc.port = {
      postMessage: (chunk) => {
        postedChunks.push(new Int16Array(chunk));
      }
    };

    // 440 Hz sine wave across 20 chunks of 128 samples (2560 input samples)
    const totalSamples = 128 * 20;
    const fullSignal = new Float32Array(totalSamples);
    for (let i = 0; i < totalSamples; i++) {
      fullSignal[i] = Math.sin(2 * Math.PI * 440 * i / sr);
    }

    // Feed 128-sample blocks
    for (let i = 0; i < totalSamples; i += 128) {
      const block = fullSignal.subarray(i, i + 128);
      proc.process([[block]], [], {});
    }

    // Gather worklet output
    const totalPosted = postedChunks.reduce((acc, c) => acc + c.length, 0);
    const workletOut = new Int16Array(totalPosted + proc.bufIndex);
    let offset = 0;
    for (const c of postedChunks) {
      workletOut.set(c, offset);
      offset += c.length;
    }
    workletOut.set(proc.buffer.subarray(0, proc.bufIndex), offset);

    // One-shot resample on the entire continuous signal
    const oneShot = resampleFloat32ToPCM16(fullSignal, sr, 16000);

    // Compare
    const lenDiff = Math.abs(workletOut.length - oneShot.length);
    let maxDiff = 0;
    const compareLen = Math.min(workletOut.length, oneShot.length);
    for (let i = 0; i < compareLen; i++) {
      const d = Math.abs(workletOut[i] - oneShot[i]);
      if (d > maxDiff) maxDiff = d;
    }

    // Maximum sample-to-sample jump check (derivative continuity)
    let maxJump = 0;
    for (let i = 1; i < workletOut.length; i++) {
      const jump = Math.abs(workletOut[i] - workletOut[i - 1]);
      if (jump > maxJump) maxJump = jump;
    }

    // For a 440 Hz sine wave at 16000 Hz, angular step is ~0.172 rad, max derivative jump ~5655 units
    const jumpThreshold = 6000;
    const passesDrift = maxDiff <= 2; // Allow at most 2 units tolerance on float-to-int rounding
    const passesLength = lenDiff <= 1; // Within 1 sample tail difference
    const passesJump = maxJump <= jumpThreshold;

    console.log(`[TEST] sampleRate=${sr} Hz:`);
    console.log(`  worklet length: ${workletOut.length}, one-shot length: ${oneShot.length} (diff: ${lenDiff})`);
    console.log(`  max absolute sample error: ${maxDiff}`);
    console.log(`  max consecutive jump: ${maxJump} (limit: ${jumpThreshold})`);

    if (passesDrift && passesLength && passesJump) {
      console.log(`[PASS] Streaming resampler at ${sr} Hz continuous and in-phase.\n`);
    } else {
      console.error(`[FAIL] Streaming resampler at ${sr} Hz failed (drift=${maxDiff}, lenDiff=${lenDiff}, jump=${maxJump})\n`);
      passed = false;
    }
  }

  if (!passed) {
    process.exit(1);
  }
}

runStreamingTest().catch((err) => {
  console.error(err);
  process.exit(1);
});
