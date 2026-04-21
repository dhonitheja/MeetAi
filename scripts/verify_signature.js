'use strict';

// Fails build if WIN_CSC_LINK not set - prevents unsigned release
if (process.platform === 'win32' && !process.env.WIN_CSC_LINK) {
  console.error('[Build] FATAL: WIN_CSC_LINK not set - unsigned build blocked');
  process.exit(1);
}

console.log('[Build] Signature config verified');
