import { defineConfig } from '@playwright/test';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  testDir: __dirname,
  timeout: 30000,
  retries: 1,
  reporter: [['html', { outputFolder: 'tests/e2e/report' }], ['line']],
  use: {
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'electron',
      use: {
        // Path to built executable  adjust for platform
        executablePath: path.join(__dirname, '../../dist/win-unpacked/MeetAi.exe'),
      },
    },
  ],
});

