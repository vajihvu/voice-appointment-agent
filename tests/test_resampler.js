/**
 * Node.js test verifying static/js/resampler.js parity against golden test vectors.
 */

const fs = require('fs');
const path = require('path');
const { resamplePCM16 } = require('../static/js/resampler');

const goldenPath = path.join(__dirname, 'golden_resampler_vectors.json');
const testCases = JSON.parse(fs.readFileSync(goldenPath, 'utf8'));

let passed = 0;
let total = 0;

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
      if (Math.abs(outList[i] - expected_output[i]) > 1) { // tolerance of 1 sample unit
        match = false;
        break;
      }
    }
  }

  if (match) {
    console.log(`[PASS] ${caseName}`);
    passed++;
  } else {
    console.error(`[FAIL] ${caseName}`);
    console.error(`  Expected: ${JSON.stringify(expected_output)}`);
    console.error(`  Received: ${JSON.stringify(outList)}`);
  }
}

console.log(`\nResults: ${passed}/${total} test cases passed.`);
if (passed !== total) {
  process.exit(1);
}

