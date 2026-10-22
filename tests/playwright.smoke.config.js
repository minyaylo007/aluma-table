const { defineConfig } = require('@playwright/test');
// tests/smoke.spec.js проти ОДНОРАЗОВОГО локального стеку (tools/serve-local-stack.py): статика + API + SQLite,
// база зникає разом із процесом, Telegram не задано. Порт ALUMA 8007 (~/maestro/PORTS.md), лише 127.0.0.1.
// reuseExistingServer: false — якщо 8007 уже хтось слухає, прогін падає, а не пише заявки в чужий процес.
// На ace-main: PYTHON=python3 (python там немає).
const PORT = '8007';
const URL = `http://127.0.0.1:${PORT}`;
const PYTHON = process.env.PYTHON || 'python3';
module.exports = defineConfig({
  testDir: '.', testMatch: 'smoke.spec.js',
  timeout: 45000, expect: { timeout: 8000 }, workers: 2, retries: 0,
  reporter: [['list']],
  use: { baseURL: URL, browserName: 'chromium', locale: 'he-IL', timezoneId: 'Asia/Jerusalem', screenshot: 'only-on-failure' },
  webServer: {
    command: `${PYTHON} tools/serve-local-stack.py --port ${PORT}`, cwd: '..', url: `${URL}/api/fx/health`,
    // облікові дані — ті самі, що бере smoke.spec.js (успадковане з оточення не підміняє їх)
    env: { BASE_URL: URL, ADMIN_USER: 'local', ADMIN_PASS: 'throwaway-local-stack' },
    reuseExistingServer: false, timeout: 20000,
  },
});
