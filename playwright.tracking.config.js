const { defineConfig } = require('@playwright/test');
// Події пікселя Meta і першої сторони (tests/tracking-events.spec.js) і воронка магазину (tests/shop.spec.js): dist/ через page.route, без порту й без мережі.
// Запуск: python3 build.py && npx playwright test --config playwright.tracking.config.js
// На ace-main — у рамці CLAUDE.md §8 через heavy, браузери з PLAYWRIGHT_BROWSERS_PATH=/opt/ihor/aluma-table/ms-playwright.
module.exports = defineConfig({
  testDir: './tests', testMatch: ['tracking-events.spec.js', 'shop.spec.js'],
  timeout: 60000, workers: 1, retries: 0,
  reporter: [['list']],
  use: { browserName: 'chromium', locale: 'he-IL', timezoneId: 'Asia/Jerusalem', viewport: { width: 390, height: 844 } },
});
