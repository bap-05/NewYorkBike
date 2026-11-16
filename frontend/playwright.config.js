import { defineConfig } from "@playwright/test";

const port = process.env.E2E_PORT || "5173";
const baseURL = `http://127.0.0.1:${port}`;

export default defineConfig({
  testDir: "./tests",
  workers: 1,
  timeout: 90000,
  expect: { timeout: 30000 },
  use: {
    baseURL,
    browserName: "chromium",
    headless: true,
  },
  webServer: {
    command: `npm run dev -- --port ${port}`,
    url: baseURL,
    reuseExistingServer: !process.env.CI,
    timeout: 60000,
  },
});
