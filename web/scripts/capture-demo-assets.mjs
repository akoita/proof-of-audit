import { chromium } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";

const rootDir = path.resolve(process.cwd(), "..");
const outputDir = path.join(rootDir, "docs", "assets");
const webUrl = process.env.CAPTURE_WEB_URL ?? "http://127.0.0.1:3300";

async function ensureOutputDir() {
  await mkdir(outputDir, { recursive: true });
}

async function capture() {
  await ensureOutputDir();
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 1600 } });

  await page.goto(webUrl, { waitUntil: "networkidle" });
  await page.getByText("Pick a live contract to drive the trust, stake, and challenge flow").waitFor();
  await page.screenshot({
    path: path.join(outputDir, "workbench-overview.png"),
    fullPage: true,
  });

  await page.getByRole("button", { name: /Clean Vault/i }).click();
  await page.getByRole("button", { name: "Generate claim" }).click();
  await page.getByTestId("current-audit-status").waitFor();
  await page.getByTestId("current-audit-status").filter({ hasText: "draft" }).waitFor();
  await page.screenshot({
    path: path.join(outputDir, "workbench-draft-claim.png"),
    fullPage: true,
  });

  await page.getByRole("button", { name: "Stake and publish" }).click();
  await page.getByTestId("current-audit-status").filter({ hasText: "published" }).waitFor();
  await page.getByRole("button", { name: "Open challenge" }).click();
  await page.getByTestId("current-audit-status").filter({ hasText: "resolved" }).waitFor();
  await page.screenshot({
    path: path.join(outputDir, "workbench-deterministic-resolution.png"),
    fullPage: true,
  });

  await browser.close();
}

capture().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
