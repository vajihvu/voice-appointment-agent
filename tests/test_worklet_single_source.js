/**
 * Node.js test that loads pcm_worklet.js logic indirectly via resampler.js
 * and verifies the worklet's resampling produces identical output to the
 * golden test vectors. This ensures pcm_worklet.js's import of resampler.js
 * uses the exact same algorithm as the standalone resampler.
 *
 * NOTE: AudioWorkletProcessor and `registerProcessor` do not exist in Node.js.
 * This test verifies that the *shared module* (resampler.js) that pcm_worklet.js
 * imports produces correct output. Full browser AudioWorklet integration
 * requires manual testing.
 */

const fs = require('fs');
const path = require('path');
const { resamplePCM16, resampleFloat32ToPCM16 } = require('../static/js/resampler');

const goldenPath = path.join(__dirname, 'golden_resampler_vectors.json');
const testCases = JSON.parse(fs.readFileSync(goldenPath, 'utf8'));

let passed = 0;
let total = 0;

// Test 1: Verify resamplePCM16 against golden vectors (same as test_resampler.js)
for (const [caseName, data] of Object.entries(testCases)) {
  total++;
  const { source_rate, target_rate, input_samples, expected_output } = data;
  const inArray = new Int16Array(input_samples);
  const outArray = resamplePCM16(inArray, source_rate, target_rate);
  const outList = Array.from(outArray);

  let match = true;
  if (outList.length !== expected_output.length) {
    match = false;
  } else {
    for (let i = 0; i < outList.length; i++) {
      if (Math.abs(outList[i] - expected_output[i]) > 1) {
        match = false;
        break;
      }
    }
  }

  if (match) {
    console.log(`[PASS] PCM16 golden: ${caseName}`);
    passed++;
  } else {
    console.error(`[FAIL] PCM16 golden: ${caseName}`);
    console.error(`  Expected: ${JSON.stringify(expected_output)}`);
    console.error(`  Received: ${JSON.stringify(outList)}`);
  }
}

// Test 2: Verify resampleFloat32ToPCM16 (the function pcm_worklet.js uses)
// Feed Float32 samples through the same path the worklet uses and compare.
{
  total++;
  const caseName = 'float32_48k_to_16k_via_worklet_path';
  // Create a Float32 sine wave at 48kHz, 30 samples
  const sourceRate = 48000;
  const targetRate = 16000;
  const floatInput = new Float32Array(30);
  for (let i = 0; i < 30; i++) {
    floatInput[i] = Math.sin(2 * Math.PI * 440 * i / sourceRate);
  }

  // Convert Float32 to Int16 manually (matching resampler.js logic)
  const int16Input = new Int16Array(floatInput.length);
  for (let i = 0; i < floatInput.length; i++) {
    const clamped = Math.max(-1.0, Math.min(1.0, floatInput[i]));
    int16Input[i] = clamped < 0 ? Math.round(clamped * 32768) : Math.round(clamped * 32767);
  }
  const expectedOutput = resamplePCM16(int16Input, sourceRate, targetRate);

  // Now use the combined function
  const actualOutput = resampleFloat32ToPCM16(floatInput, sourceRate, targetRate);

  let match = true;
  if (actualOutput.length !== expectedOutput.length) {
    match = false;
  } else {
    for (let i = 0; i < actualOutput.length; i++) {
      if (Math.abs(actualOutput[i] - expectedOutput[i]) > 1) {
        match = false;
        break;
      }
    }
  }

  if (match) {
    console.log(`[PASS] Float32 worklet path: ${caseName}`);
    passed++;
  } else {
    console.error(`[FAIL] Float32 worklet path: ${caseName}`);
    console.error(`  Expected length: ${expectedOutput.length}, Got: ${actualOutput.length}`);
    console.error(`  Expected: ${JSON.stringify(Array.from(expectedOutput))}`);
    console.error(`  Received: ${JSON.stringify(Array.from(actualOutput))}`);
  }
}

// Test 3: Verify pcm_worklet.js file actually imports from resampler.js
{
  total++;
  const caseName = 'pcm_worklet_imports_resampler';
  const workletSource = fs.readFileSync(
    path.join(__dirname, '..', 'static', 'js', 'pcm_worklet.js'),
    'utf8'
  );
  const hasImport = (workletSource.includes("from './resampler.js'") || workletSource.includes('from "./resampler.js"'))
                 && (workletSource.includes('StreamingResampler') || workletSource.includes('resampleFloat32ToPCM16'));
  const hasNoInlineAlgorithm = !workletSource.includes('while (this.pos');

  if (hasImport && hasNoInlineAlgorithm) {
    console.log(`[PASS] ${caseName}: worklet imports shared module, no inline copy`);
    passed++;
  } else {
    console.error(`[FAIL] ${caseName}: hasImport=${hasImport}, hasNoInlineAlgorithm=${hasNoInlineAlgorithm}`);
  }
}

// Test 4: Verify index.html has no inline worklet algorithm copy
{
  total++;
  const caseName = 'index_html_no_inline_algorithm';
  const htmlSource = fs.readFileSync(
    path.join(__dirname, '..', 'static', 'index.html'),
    'utf8'
  );
  const hasWorkletCode = htmlSource.includes('const workletCode');
  const hasBlobFallback = htmlSource.includes('new Blob([workletCode]');

  if (!hasWorkletCode && !hasBlobFallback) {
    console.log(`[PASS] ${caseName}: no inline worklet copy or Blob fallback in index.html`);
    passed++;
  } else {
    console.error(`[FAIL] ${caseName}: hasWorkletCode=${hasWorkletCode}, hasBlobFallback=${hasBlobFallback}`);
  }
}

console.log(`\nResults: ${passed}/${total} test cases passed.`);
if (passed !== total) {
  process.exit(1);
}

