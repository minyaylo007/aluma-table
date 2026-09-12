const { defineConfig, devices } = require('@playwright/test');
module.exports = defineConfig({
  testDir: './tests',
  timeout: 45000,
  expect: { timeout: 8000 },
  reporter: [['list']],
  retries: 1,
  workers: 3,
  use: {
    baseURL: process.env.BASE_URL || 'https://table.central-aparts.store',
    ...devices['Desktop Chrome'],
    viewport: { width: 390, height: 844 },
    isMobile: false,
    locale: 'he-IL',
    timezoneId: 'Asia/Jerusalem',
    screenshot: 'only-on-failure',
  },
});
