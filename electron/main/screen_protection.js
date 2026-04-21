'use strict';

/**
 * Electron main-process screen capture exclusion.
 *
 * win.setContentProtection(true) maps to:
 *   Windows -> SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)
 *   macOS   -> [NSWindow setSharingType: NSWindowSharingNone]
 *
 * No user input is passed to this API - protection is binary on/off only.
 */

class ElectronScreenProtection {
  /**
   * Apply screen capture exclusion to a BrowserWindow.
   * Safe to call multiple times - idempotent.
   * @param {import('electron').BrowserWindow} win
   * @returns {boolean} True if applied successfully
   */
  static apply(win) {
    if (!win || win.isDestroyed()) {
      console.error('[ScreenProtection] Window is null or destroyed');
      return false;
    }
    try {
      win.setContentProtection(true);
      console.log('[ScreenProtection] Applied - window id:', win.id);
      return true;
    } catch (err) {
      console.error('[ScreenProtection] Failed:', err.message);
      return false;
    }
  }

  /**
   * Re-apply protection after window recreation. Alias for apply().
   * @param {import('electron').BrowserWindow} win
   * @returns {boolean}
   */
  static reapply(win) {
    return ElectronScreenProtection.apply(win);
  }

  /**
   * Remove protection. DEBUG ONLY - never call in production builds.
   * @param {import('electron').BrowserWindow} win
   */
  static remove(win) {
    if (!win || win.isDestroyed()) return;
    win.setContentProtection(false);
    console.warn('[ScreenProtection] REMOVED - debug only, do not ship');
  }
}

module.exports = { ElectronScreenProtection };
