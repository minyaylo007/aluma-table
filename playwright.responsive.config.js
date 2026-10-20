const { defineConfig } = require('@playwright/test');
// Верстка на всіх екранах (tests/responsive.spec.js): dist/ через page.route, без порту, без webServer і без прода.
// Запуск: python3 build.py && npx playwright test --config playwright.responsive.config.js
// На ace-main — у рамці CLAUDE.md §8 через heavy, браузери з PLAYWRIGHT_BROWSERS_PATH=/opt/ihor/aluma-table/ms-playwright.
module.exports = defineConfig({
  testDir: './tests', testMatch: 'responsive.spec.js',
  timeout: 120000, workers: 1, retries: 0,
  reporter: [['list']],
  use: { browserName: 'chromium', locale: 'he-IL', timezoneId: 'Asia/Jerusalem' },
});
