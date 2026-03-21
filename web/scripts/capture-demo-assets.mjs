import { chromium } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";

const rootDir = path.resolve(process.cwd(), "..");
const outputDir = path.join(rootDir, "docs", "assets");
const webUrl = process.env.CAPTURE_WEB_URL ?? "http://127.0.0.1:3300";
const TIMEOUT = 60_000;

async function ensureOutputDir() {
  await mkdir(outputDir, { recursive: true });
}

async function capture() {
  await ensureOutputDir();
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 1600 } });

  // Wait for the workbench to finish its initial data load (auditor-service-select is
  // rendered only after the workspace API calls resolve).
  await page.goto(webUrl, { waitUntil: "networkidle" });
  await page.getByTestId("auditor-service-select").waitFor({ timeout: TIMEOUT });
  await page.screenshot({
    path: path.join(outputDir, "workbench-overview.png"),
    fullPage: true,
  });

  // Select the Clean Vault fixture and run the security analysis.
  await page.getByRole("button", { name: /Clean Vault/i }).click();
  await page.getByTestId("submit-audit").click();
  await page.getByTestId("current-audit-status").waitFor({ timeout: TIMEOUT });
  await page.getByTestId("current-audit-status").filter({ hasText: "draft" }).waitFor({ timeout: TIMEOUT });
  await page.screenshot({
    path: path.join(outputDir, "workbench-draft-claim.png"),
    fullPage: true,
  });

  // Publish on-chain (stake), then challenge the claim.
  await page.getByTestId("publish-btn").click();
  await page.getByTestId("current-audit-status").filter({ hasText: "published" }).waitFor({ timeout: TIMEOUT });
  await page.getByTestId("challenge-btn").click();
  await page.getByTestId("current-audit-status").filter({ hasText: /challenged|resolved/ }).waitFor({ timeout: TIMEOUT });
  await page.screenshot({
    path: path.join(outputDir, "workbench-challenge-resolution.png"),
    fullPage: true,
  });

  await browser.close();
}

capture().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
