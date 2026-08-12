const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './tests/e2e',
  testMatch: /tutorial-video\.spec\.js/,
  timeout: 180000,
  expect: { timeout: 10000 },
  retries: 0,
  workers: 1,
  reporter: [['line'], ['html', { outputFolder: 'test-results/tutorial-report', open: 'never' }]],
  outputDir: 'test-results/tutorial',
  use: {
    baseURL: process.env.MESFLOW_BASE_URL || 'http://127.0.0.1:8080',
    viewport: { width: 1920, height: 1080 },
    video: { mode: 'on', size: { width: 1920, height: 1080 } },
    trace: 'off',
    screenshot: 'only-on-failure',
  },
});
