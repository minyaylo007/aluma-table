const crypto = require('crypto');
const { defineConfig } = require('@playwright/test');
// tests/smoke.spec.js проти ОДНОРАЗОВОГО локального стеку (tools/serve-local-stack.py): статика + API + SQLite,
// база зникає разом із процесом, Telegram не задано. Порт ALUMA 8007 (~/maestro/PORTS.md), лише 127.0.0.1.
// reuseExistingServer: false — якщо 8007 уже хтось слухає, прогін падає, а не пише заявки в чужий процес.
// На ace-main: PYTHON=python3 (python там немає).
const PORT = '8007';
const URL = `http://127.0.0.1:${PORT}`;
const PYTHON = process.env.PYTHON || 'python3';
// Вхід в адмінку стеку — випадковий на кожен прогін: у коді значення нема. Конфіг читається й у воркерах;
// змінна, виставлена тут у головному процесі, переходить до них, тож стек і тест бачать те саме.
process.env.SMOKE_ADMIN_USER = process.env.SMOKE_ADMIN_USER || 'smoke';
process.env.SMOKE_ADMIN_KEY = process.env.SMOKE_ADMIN_KEY || crypto.randomBytes(18).toString('hex');
module.exports = defineConfig({
  testDir: '.', testMatch: 'smoke.spec.js',
  timeout: 45000, expect: { timeout: 8000 }, workers: 2, retries: 0,
  reporter: [['list']],
  use: { baseURL: URL, browserName: 'chromium', locale: 'he-IL', timezoneId: 'Asia/Jerusalem', screenshot: 'only-on-failure' },
  webServer: {
    command: `${PYTHON} tools/serve-local-stack.py --port ${PORT}`, cwd: '..', url: `${URL}/api/fx/health`,
    // ті самі облікові дані, що бере smoke.spec.js (успадковані з оточення не підміняють їх)
    env: { BASE_URL: URL, ADMIN_USER: process.env.SMOKE_ADMIN_USER, ADMIN_PASS: process.env.SMOKE_ADMIN_KEY },
    reuseExistingServer: false, timeout: 20000,
  },
});
