'use strict';

const { autoUpdater } = require('electron-updater');
const { ipcMain, BrowserWindow } = require('electron');

/**
 * MeetAI auto-updater using electron-updater.
 *
 * SECURITY REQUIREMENTS:
 * 1. Feed URL is a hardcoded string literal - NEVER read from config,
 *    env var, or API response. Prevents update hijacking.
 * 2. autoUpdater.autoDownload = false - user initiates download.
 * 3. Signature verification enforced by electron-updater by default.
 *    Never set disableWebInstaller or skipSignatureValidation.
 * 4. Update events are forwarded to overlay renderer only - no shell exec.
 */

// HARDCODED - never read from config, env, or API
const UPDATE_FEED_URL = 'https://github.com/dhonitheja/MeetAi/releases/latest/download';

let _overlayWin = null;
let _handlersRegistered = false;
let _startupCheckScheduled = false;

function setupAutoUpdater(overlayWin) {
  _overlayWin = overlayWin;

  // Feed URL - hardcoded string literal only
  autoUpdater.setFeedURL({
    provider: 'github',
    owner: 'dhonitheja',
    repo: 'MeetAi',
  });

  // Never auto-download - show notification first
  autoUpdater.autoDownload = false;   // must remain - double protection
  autoUpdater.autoInstallOnAppQuit = true;

  autoUpdater.removeAllListeners('checking-for-update');
  autoUpdater.removeAllListeners('update-available');
  autoUpdater.removeAllListeners('update-not-available');
  autoUpdater.removeAllListeners('download-progress');
  autoUpdater.removeAllListeners('update-downloaded');
  autoUpdater.removeAllListeners('error');

  // Forward update events to renderer
  autoUpdater.on('checking-for-update', () => {
    sendToOverlay('update:status', { type: 'checking' });
  });

  autoUpdater.on('update-available', (info) => {
    sendToOverlay('update:status', {
      type: 'available',
      version: info.version,
      releaseDate: info.releaseDate,
    });
    // Download only starts when user clicks Download in UpdateToast.jsx
    // which calls window.electronAPI.invoke('download-update')
    // which triggers the 'download-update' ipcMain.handle below
  });

  autoUpdater.on('update-not-available', () => {
    sendToOverlay('update:status', { type: 'not-available' });
  });

  autoUpdater.on('download-progress', (progress) => {
    sendToOverlay('update:status', {
      type: 'progress',
      percent: Math.round(progress.percent),
      bytesPerSecond: progress.bytesPerSecond,
    });
  });

  autoUpdater.on('update-downloaded', (info) => {
    sendToOverlay('update:status', {
      type: 'downloaded',
      version: info.version,
    });
  });

  autoUpdater.on('error', (err) => {
    // Log error but never expose stack trace to renderer
    console.error('[AutoUpdater] Error:', err.message);
    sendToOverlay('update:status', {
      type: 'error',
      message: 'Update check failed',
    });
  });

  if (!_handlersRegistered) {
    // IPC: renderer requests update check
    ipcMain.handle('check-for-updates', async () => {
      try {
        await autoUpdater.checkForUpdates();
        return { status: 'checking' };
      } catch (err) {
        console.error('[AutoUpdater] Check failed:', err.message);
        return { status: 'error', message: 'Update check failed' };
      }
    });

    // IPC: renderer requests download
    ipcMain.handle('download-update', async () => {
      try {
        await autoUpdater.downloadUpdate();
        return { status: 'downloading' };
      } catch (err) {
        console.error('[AutoUpdater] Download failed:', err.message);
        return { status: 'error' };
      }
    });

    // IPC: renderer requests install
    ipcMain.on('install-now', () => {
      console.log('[AutoUpdater] Installing update and restarting');
      autoUpdater.quitAndInstall(false, true);
    });

    _handlersRegistered = true;
  }

  console.log('[AutoUpdater] Configured for github/dhonitheja/MeetAi');
  console.log('[AutoUpdater] Feed locked to:', UPDATE_FEED_URL);
}

function sendToOverlay(channel, data = {}) {
  if (_overlayWin && !_overlayWin.isDestroyed()) {
    _overlayWin.webContents.send(channel, data);
  }
}

function checkForUpdatesOnStartup() {
  if (_startupCheckScheduled) return;
  _startupCheckScheduled = true;

  // Delay 5 seconds after launch - avoid slowing startup
  setTimeout(async () => {
    try {
      await autoUpdater.checkForUpdates();
    } catch (err) {
      console.error('[AutoUpdater] Startup check failed:', err.message);
    }
  }, 5000);
}

module.exports = { setupAutoUpdater, checkForUpdatesOnStartup };
