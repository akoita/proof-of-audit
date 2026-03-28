import { defineConfig } from "@playwright/test";

const webUrl = process.env.E2E_WEB_URL ?? "http://127.0.0.1:3300";
const useWebServer = process.env.E2E_SKIP_WEB_SERVER !== "1";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  timeout: 120_000,
  use: {
    baseURL: webUrl,
    trace: "on-first-retry",
  },
  webServer: useWebServer
    ? {
        command: "../scripts/run-e2e-stack.sh",
        url: webUrl,
        reuseExistingServer: false,
        stdout: "pipe",
        stderr: "pipe",
        timeout: 240_000,
      }
    : undefined,
});
