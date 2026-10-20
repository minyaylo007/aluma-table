const { defineConfig } = require('@playwright/test');
// Доступність (tests/a11y.spec.js): dist/ через page.route, без порту, без webServer і без прода.
// Запуск: python3 build.py && npx playwright test --config playwright.a11y.config.js
// На ace-main — у рамці CLAUDE.md §8 через heavy, браузери з PLAYWRIGHT_BROWSERS_PATH=/opt/ihor/aluma-table/ms-playwright.
module.exports = defineConfig({
  testDir: './tests', testMatch: 'a11y.spec.js',
  timeout: 45000, workers: 3, retries: 0,
  reporter: [['list']],
  use: { browserName: 'chromium', locale: 'he-IL', timezoneId: 'Asia/Jerusalem' },
});
