const { defineConfig } = require('@playwright/test');
// Порт перегляду — PREVIEW_PORT (типово 4173), той самий читає tools/serve-preview.py.
// На ace-main: PREVIEW_PORT=8007 (порт ALUMA з ~/maestro/PORTS.md) і PYTHON=python3 (python там немає).
const PORT = process.env.PREVIEW_PORT || '4173';
const URL = `http://127.0.0.1:${PORT}`;
const PYTHON = process.env.PYTHON || 'python';
module.exports = defineConfig({
  testDir: './tests', testMatch: 'redesign.spec.js',
  timeout: 30000, expect: { timeout: 7000 }, workers: 3, retries: 0,
  reporter: [['list']],
  use: { baseURL: URL, browserName: 'chromium', screenshot: 'only-on-failure', trace: 'retain-on-failure' },
  webServer: { command: `${PYTHON} tools/serve-preview.py`, url: URL, env: { PREVIEW_PORT: PORT }, reuseExistingServer: true, timeout: 15000 },
});
