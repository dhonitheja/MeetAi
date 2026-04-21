'use strict';

const { exec } = require('child_process');

/**
 * Meeting app process names to detect per platform.
 */
const MEETING_PROCESSES = {
  win32: ['Zoom.exe', 'Teams.exe', 'chrome.exe', 'CiscoWebexMeetings.exe', 'slack.exe'],
  darwin: ['zoom.us', 'Microsoft Teams', 'Google Chrome', 'Cisco Webex Meetings', 'Slack'],
  linux: [],
};

/**
 * Polls running processes every 2 seconds to detect active meeting apps.
 * Fires callbacks when meeting apps start or stop.
 * Used to re-apply screen protection when overlay window is recreated.
 *
 * Security: exec() output is used only for string matching.
 * It is never passed to eval(), shell expansion, or any interpreter.
 */
class ShareDetector {
  /**
   * @param {() => void} onShareStart - Fired when meeting app first detected
   * @param {() => void} onShareEnd   - Fired when all meeting apps closed
   */
  constructor(onShareStart, onShareEnd) {
    this.onShareStart = onShareStart;
    this.onShareEnd = onShareEnd;
    this.isSharing = false;
    this._interval = null;
  }

  /**
   * Start polling. Safe to call multiple times - will not double-start.
   */
  start() {
    if (this._interval) return;
    this._interval = setInterval(() => this._poll(), 2000);
    console.log('[ShareDetector] Monitoring started');
  }

  /**
   * Stop polling and clean up interval.
   */
  stop() {
    if (this._interval) {
      clearInterval(this._interval);
      this._interval = null;
      console.log('[ShareDetector] Monitoring stopped');
    }
  }

  _poll() {
    const currentPlatform = process.platform;
    const targets = MEETING_PROCESSES[currentPlatform] || [];
    if (targets.length === 0) {
      // Linux: process monitoring not supported - screen protection applied statically
      return;
    }

    const cmd = currentPlatform === 'win32'
      ? 'tasklist /FO CSV /NH'
      : 'ps -e -o comm=';

    // timeout: 3000 prevents hanging if process list is slow
    exec(cmd, { timeout: 3000 }, (err, stdout) => {
      if (err) return;

      // stdout is untrusted external data.
      // Used ONLY for toLowerCase().includes() string matching.
      // Never passed to eval(), shell, or any interpreter.
      const normalised = stdout.toLowerCase();
      const running = targets.some((name) =>
        normalised.includes(name.toLowerCase())
      );

      if (running && !this.isSharing) {
        this.isSharing = true;
        console.log('[ShareDetector] Meeting app detected');
        try {
          this.onShareStart?.();
        } catch (e) {
          console.error('[ShareDetector] onShareStart threw:', e.message);
        }
      } else if (!running && this.isSharing) {
        this.isSharing = false;
        console.log('[ShareDetector] Meeting app closed');
        try {
          this.onShareEnd?.();
        } catch (e) {
          console.error('[ShareDetector] onShareEnd threw:', e.message);
        }
      }
    });
  }
}

module.exports = { ShareDetector };
