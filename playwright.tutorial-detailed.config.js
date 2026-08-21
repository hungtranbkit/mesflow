const { defineConfig } = require('@playwright/test');
const fs=require('fs');
const tutorialConfig=JSON.parse(fs.readFileSync('./tutorial/tutorial.config.json','utf8'));
const authState=process.env.MESFLOW_TUTORIAL_AUTH_STATE||'tutorial-auth-state.json';
module.exports = defineConfig({
  testDir:'./tests/e2e',
  testMatch:/tutorial-(?:detailed|coverage)\.spec\.js/,
  timeout:tutorialConfig.tutorial_speed.module_timeout_ms,
  expect:{timeout:10000},
  retries:0,
  workers:1,
  reporter:[['line']],
  outputDir:'test-results/tutorial-detailed',
  use:{
    baseURL:process.env.MESFLOW_BASE_URL||'http://127.0.0.1:8080',
    storageState:fs.existsSync(authState)?authState:undefined,
    viewport:{width:1920,height:1080},
    video:{mode:'on',size:{width:1920,height:1080}},
    trace:'off',
    screenshot:'only-on-failure'
  }
});
