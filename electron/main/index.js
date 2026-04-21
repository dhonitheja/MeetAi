'use strict';

const path = require('path');
const { app, BrowserWindow } = require('electron');
const { ElectronScreenProtection } = require('./screen_protection');
const { ShareDetector } = require('./share_detector');
const { registerShortcuts, unregisterShortcuts } = require('./keyboard_shortcuts');
const { setupAutoUpdater, checkForUpdatesOnStartup } = require('./auto_updater');

let overlayWin = null;
let detector = null;

function createOverlayWindow() {
  overlayWin = new BrowserWindow({
    width: 420,
    height: 640,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    resizable: true, // Allow resize during dev/polish
    skipTaskbar: true,
    webPreferences: {
      preload: path.join(__dirname, '..', 'renderer', 'preload', 'shortcuts_api.js'),
      contextIsolation: true,
      nodeIntegration: false,
      additionalArguments: ['--is-overlay'],
    },
  });

  const indexPath = path.join(__dirname, '..', '..', 'index.html');
  overlayWin.loadFile(indexPath).catch(() => {
    overlayWin.loadURL('about:blank');
  });

  setupAutoUpdater(overlayWin);
  checkForUpdatesOnStartup();

  ElectronScreenProtection.apply(overlayWin);

  detector = new ShareDetector(
    () => ElectronScreenProtection.reapply(overlayWin),
    () => console.log('[ShareDetector] Meeting app closed - protection stays active')
  );
  detector.start();

  overlayWin.webContents.on('did-finish-load', () => {
    registerShortcuts(overlayWin); // main triggers - renderer never can
  });

  overlayWin.on('closed', () => detector.stop());
}

app.whenReady().then(() => {
  createOverlayWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createOverlayWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('will-quit', () => {
  unregisterShortcuts();
});
