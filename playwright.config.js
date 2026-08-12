const { defineConfig } = require('@playwright/test');
module.exports = defineConfig({
  testDir: './tests/e2e',
  timeout: 30000,
  expect: { timeout: 7000 },
  retries: 1,
  workers: 1,
  reporter: [['line'], ['junit', { outputFile: 'test-results/playwright.xml' }], ['html', { outputFolder: 'test-results/playwright-report', open: 'never' }]],
  use: { baseURL: process.env.MESFLOW_BASE_URL || 'http://127.0.0.1:8080', trace: 'retain-on-failure', screenshot: 'only-on-failure' }
});
