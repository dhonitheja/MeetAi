'use strict';

const { globalShortcut } = require('electron');

/**
 * Keyboard shortcuts for MeetAI overlay.
 *
 * SECURITY: All globalShortcut registration happens in the main process only.
 * The renderer never registers global shortcuts.
 * This prevents zombie listeners if the renderer crashes or reloads.
 *
 * F9:  Toggle overlay window visibility
 * F10: Trigger voice speak (speak last co-pilot suggestion)
 * F11: Toggle face swap on/off
 */

let _overlayWin = null;
let _registered = false;

/**
 * Register all global shortcuts.
 * @param {import('electron').BrowserWindow} overlayWin
 * @returns {void}
 */
function registerShortcuts(overlayWin) {
  if (_registered) {
    console.warn('[Shortcuts] Already registered - skipping');
    return;
  }

  _overlayWin = overlayWin;

  // F9 - Toggle overlay visibility
  const f9 = globalShortcut.register('F9', () => {
    if (!_overlayWin || _overlayWin.isDestroyed()) return;
    if (_overlayWin.isVisible()) {
      _overlayWin.hide();
    } else {
      _overlayWin.show();
      _overlayWin.focus();
    }
  });
  if (!f9) console.error('[Shortcuts] F9 registration failed - key may be in use');

  // F10 - Trigger voice speak in renderer
  const f10 = globalShortcut.register('F10', () => {
    if (!_overlayWin || _overlayWin.isDestroyed()) return;
    _overlayWin.webContents.send('shortcut:voice-speak');
  });
  if (!f10) console.error('[Shortcuts] F10 registration failed');

  // F11 - Toggle face swap via renderer
  const f11 = globalShortcut.register('F11', () => {
    if (!_overlayWin || _overlayWin.isDestroyed()) return;
    _overlayWin.webContents.send('shortcut:face-toggle');
  });
  if (!f11) console.error('[Shortcuts] F11 registration failed');

  _registered = true;
  console.log('[Shortcuts] F9/F10/F11 registered');
}

/**
 * Unregister all global shortcuts.
 * Must be called on app 'will-quit' to prevent OS-level shortcut leaks.
 * @returns {void}
 */
function unregisterShortcuts() {
  globalShortcut.unregisterAll();
  _registered = false;
  _overlayWin = null;
  console.log('[Shortcuts] All shortcuts unregistered');
}



module.exports = { registerShortcuts, unregisterShortcuts };
