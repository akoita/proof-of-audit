import { defineConfig } from "@playwright/test";

const webUrl = process.env.E2E_WEB_URL ?? "http://127.0.0.1:3300";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  timeout: 120_000,
  use: {
    baseURL: webUrl,
    trace: "on-first-retry",
  },
  webServer: {
    command: "../scripts/run-e2e-stack.sh",
    url: webUrl,
    reuseExistingServer: !process.env.CI,
    stdout: "pipe",
    stderr: "pipe",
    timeout: 240_000,
  },
});
