/**
 * Node.js test verifying static/js/resampler.js evaluates cleanly in a browser-like
 * ES module environment where the `module` global does not exist.
 */

const fs = require('fs');
const path = require('path');
const vm = require('vm');

function testBrowserEvaluation() {
  const filePath = path.join(__dirname, '../static/js/resampler.js');
  const code = fs.readFileSync(filePath, 'utf8');

  // In a browser module context, `module` is undefined.
  // We strip the ES `export` keyword solely so standard VM Script can parse it without a loader,
  // while strictly keeping `module` undefined in the global context.
  const browserCode = code.replace(/^export\s+\{[^}]+\};/m, '// export stripped for VM execution');

  const sandbox = {
    Float32Array,
    Int16Array,
    Math,
    console
  };
  // Ensure `module` is not defined
  delete sandbox.module;

  try {
    vm.createContext(sandbox);
    vm.runInContext(browserCode, sandbox);
    console.log('[PASS] Evaluated resampler.js with module=undefined: no ReferenceError thrown.');
  } catch (err) {
    console.error('[FAIL] Evaluation failed when module=undefined:', err);
    process.exit(1);
  }

  // Also verify with native dynamic import (ES module mode)
  import('file:///' + path.resolve(filePath).replace(/\\/g, '/'))
    .then((mod) => {
      if (typeof mod.StreamingResampler === 'function' &&
          typeof mod.resamplePCM16 === 'function' &&
          typeof mod.resampleFloat32ToPCM16 === 'function') {
        console.log('[PASS] ES module dynamic import exported all functions successfully.');
      } else {
        console.error('[FAIL] Missing exported symbols from ES module import.');
        process.exit(1);
      }
    })
    .catch((err) => {
      console.error('[FAIL] ES module import threw:', err);
      process.exit(1);
    });
}

testBrowserEvaluation();
