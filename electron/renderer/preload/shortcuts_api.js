'use strict';

const { contextBridge, ipcRenderer } = require('electron');

const LISTEN_CHANNELS = new Set([
  'shortcut:voice-speak',
  'shortcut:face-toggle',
  'update:checking',
  'update:not-available',
  'update:status',
]);

const INVOKE_CHANNELS = new Set([
  'check-for-updates',
  'download-update',
]);

const SEND_CHANNELS = new Set([
  'install-now',
  'update:check',
  'update:install',
]);

/**
 * Subscribe to voice-speak shortcut events from main process.
 * @param {(event: import('electron').IpcRendererEvent, ...args: any[]) => void} cb
 * @returns {void}
 */
function onVoiceSpeak(cb) {
  ipcRenderer.on('shortcut:voice-speak', cb);
}

/**
 * Subscribe to face-toggle shortcut events from main process.
 * @param {(event: import('electron').IpcRendererEvent, ...args: any[]) => void} cb
 * @returns {void}
 */
function onFaceToggle(cb) {
  ipcRenderer.on('shortcut:face-toggle', cb);
}

/**
 * Remove all shortcut listeners from this renderer process.
 * @returns {void}
 */
function removeAll() {
  ipcRenderer.removeAllListeners('shortcut:voice-speak');
  ipcRenderer.removeAllListeners('shortcut:face-toggle');
}



/**
 * Subscribe to IPC events for allowlisted channels.
 * @param {string} channel
 * @param {(event: import('electron').IpcRendererEvent, ...args: any[]) => void} cb
 * @returns {void}
 */
function on(channel, cb) {
  if (!LISTEN_CHANNELS.has(channel) || typeof cb !== 'function') return;
  ipcRenderer.on(channel, cb);
}

/**
 * Invoke an IPC handler for allowlisted channels.
 * @param {string} channel
 * @param {...any} args
 * @returns {Promise<any>}
 */
function invoke(channel, ...args) {
  if (!INVOKE_CHANNELS.has(channel)) {
    return Promise.resolve({ status: 'error', message: 'Channel not allowed' });
  }
  return ipcRenderer.invoke(channel, ...args);
}

/**
 * Send one-way IPC message on allowlisted channels.
 * @param {string} channel
 * @param {...any} args
 * @returns {void}
 */
function send(channel, ...args) {
  if (!SEND_CHANNELS.has(channel)) return;
  ipcRenderer.send(channel, ...args);
}

/**
 * Remove listeners for an allowlisted channel.
 * @param {string} channel
 * @returns {void}
 */
function removeAllListeners(channel) {
  if (!LISTEN_CHANNELS.has(channel)) return;
  ipcRenderer.removeAllListeners(channel);
}

/**
 * Expose shortcut and updater event listener API to renderer via contextBridge.
 * Renderer subscribes to shortcut events but never registers them.
 */
contextBridge.exposeInMainWorld('shortcuts', {
  onVoiceSpeak: (cb) => ipcRenderer.on('shortcut:voice-speak', cb),
  onFaceToggle: (cb) => ipcRenderer.on('shortcut:face-toggle', cb),
  removeAll: () => {
    ipcRenderer.removeAllListeners('shortcut:voice-speak');
    ipcRenderer.removeAllListeners('shortcut:face-toggle');
  },
});

/**
 * Expose an allowlisted IPC bridge for updater and overlay events.
 */
contextBridge.exposeInMainWorld('electronAPI', {
  on,
  invoke,
  send,
  removeAllListeners,
});
