import { expect, Page, test } from "@playwright/test";

async function openWorkbench(page: Page) {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Audit Workbench" })).toBeVisible();
  await expect(page.getByRole("heading", { name: /Demo Fixtures/i })).toBeVisible();
}

async function createAuditFromFixture(page: Page, fixtureName: RegExp) {
  await openWorkbench(page);
  await page.getByRole("button", { name: fixtureName }).click();
  await page.getByTestId("submit-audit").click();
  await expect(page.getByTestId("current-audit-status")).toHaveText("draft");
  await expect(page.getByText("Detailed Analysis Findings", { exact: true })).toBeVisible();
}

async function publishActiveAudit(page: Page) {
  await page.getByTestId("publish-btn").click();
  await expect(page.getByTestId("current-audit-status")).toHaveText("published");
}

test("fixture audit can be created, published, and challenged onto manual fallback", async ({ page }) => {
  await createAuditFromFixture(page, /Clean Vault/i);

  await expect(
    page.getByText(/No benchmark issue found across the supported checks/i).first(),
  ).toBeVisible();
  await expect(page.getByText("Evidence Verification Hashes", { exact: true })).toBeVisible();

  await publishActiveAudit(page);
  await page.getByTestId("challenge-btn").click();

  await expect(page.getByTestId("current-audit-status")).toHaveText("challenged");
  await expect(page.getByText("Challenge & Resolution", { exact: true })).toBeVisible();
  await expect(page.getByText("Manual Fallback", { exact: true })).toBeVisible();
  await expect(page.getByText(/Plain proof-URI challenges require manual review/i)).toBeVisible();
});

test("source bundle mode can submit without a deployed address", async ({ page }) => {
  await openWorkbench(page);

  const submitButton = page.getByTestId("submit-audit");
  await page.getByRole("button", { name: "Source bundle" }).click();
  await expect(submitButton).toBeDisabled();

  await page
    .getByPlaceholder("ipfs://... or https://...")
    .fill("https://example.com/bundles/reentrancy-bank.zip");
  await expect(submitButton).toBeEnabled();

  await submitButton.click();
  await expect(page.getByTestId("current-audit-status")).toHaveText("draft");
});

test("sidebar docs and support controls are wired", async ({ page }) => {
  await openWorkbench(page);

  await page.getByRole("button", { name: /Technical Docs/i }).click();
  await expect(page.getByRole("heading", { name: /Proof-of-Audit Documentation/i })).toBeVisible();

  await expect(page.getByRole("link", { name: /Support/i })).toHaveAttribute(
    "href",
    "https://github.com/akoita/proof-of-audit/issues",
  );
});
