import { expect, Locator, Page, test } from "@playwright/test";

async function createAuditFromFixture(page: Page, fixtureName: RegExp) {
  await page.goto("/");
  await expect(
    page.getByText("Pick a live contract to drive the trust, stake, and challenge flow"),
  ).toBeVisible();
  await expect(page.getByText("Service discovery", { exact: true })).toBeVisible();
  await expect(
    page.locator(".signal-note").getByText("Proof-of-Audit Auditor", { exact: true }),
  ).toBeVisible();
  await expect(page.locator(".signal-note").getByText("proof-of-audit-auditor")).toBeVisible();
  await expect(page.locator(".signal-note").getByText("/auditor")).toBeVisible();
  await expect(
    page.locator(".signal-note").getByText("/audits", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: fixtureName }).click();
  await page.getByRole("button", { name: "Generate claim" }).click();
  await expect(page.getByTestId("current-audit-status")).toHaveText("draft");
  await expect(page.getByText("Deterministic path ready")).toBeVisible();
}

async function publishActiveAudit(page: Page) {
  await page.getByRole("button", { name: "Stake and publish" }).click();
  await expect(page.getByTestId("current-audit-status")).toHaveText("published");
}

function challengeInput(page: Page): Locator {
  return page.locator(".action-card-wide input");
}

test("clean fixture challenge auto-resolves upheld", async ({ page }) => {
  await createAuditFromFixture(page, /Clean Vault/i);

  await expect(page.locator(".report-panel").getByText("proof-of-audit-auditor")).toBeVisible();

  await expect(
    page.getByRole("heading", {
      name: /No benchmark issue found across the supported checks/i,
    }),
  ).toBeVisible();
  await expect(page.getByText(/Curated evidence artifact for the deterministic path:/i)).toContainText(
    "ipfs://clean-vault/missed-reentrancy",
  );

  await publishActiveAudit(page);
  await page.getByRole("button", { name: "Open challenge" }).click();

  await expect(page.getByTestId("current-audit-status")).toHaveText("resolved");
  await expect(page.getByTestId("challenge-status")).toHaveText("upheld");
  await expect(page.getByText("Deterministic path", { exact: true })).toBeVisible();
  await expect(page.getByText(/Resolution upheld by deterministic-verifier/i)).toBeVisible();
  await expect(
    page.getByText(/verified: The submitted PoC demonstrates a missed issue/i),
  ).toBeVisible();
});

test("invalid challenge evidence stays open for manual review", async ({ page }) => {
  await createAuditFromFixture(page, /Clean Vault/i);
  await publishActiveAudit(page);

  await challengeInput(page).fill("ipfs://wrong-proof");
  await page.getByRole("button", { name: "Open challenge" }).click();

  await expect(page.getByTestId("current-audit-status")).toHaveText("challenged");
  await expect(page.getByTestId("challenge-status")).toHaveText("opened");
  await expect(page.getByText("Manual fallback", { exact: true })).toBeVisible();
  await expect(
    page.getByText(/invalid_evidence: The submitted PoC does not match/i),
  ).toBeVisible();
  await expect(
    page.getByText(/Provide the curated artifact ipfs:\/\/clean-vault\/missed-reentrancy/i),
  ).toBeVisible();
});

test("dual risk vault renders the richer multi-finding report", async ({ page }) => {
  await createAuditFromFixture(page, /Dual Risk Vault/i);

  await expect(
    page.getByRole("heading", {
      name: /The vault exposes both unrestricted role rotation and unchecked emergency payouts/i,
    }),
  ).toBeVisible();
  await expect(page.getByText(/Severity mix: High 1 · Medium 1/i)).toBeVisible();
  await expect(page.getByText("Missing access control on rotateOwner()")).toBeVisible();
  await expect(page.getByText("Unchecked external call in emergencyPayout()")).toBeVisible();
  await expect(page.getByText(/Access Control · High confidence · rotateOwner\(address\)/i)).toBeVisible();
  await expect(
    page.getByText(/Unchecked External Call · Medium confidence · emergencyPayout\(uint256\)/i),
  ).toBeVisible();
  await expect(page.getByText(/Evidence: ipfs:\/\/dual-risk-vault\/owner-takeover/i)).toBeVisible();
  await expect(
    page.getByText(/Evidence: ipfs:\/\/dual-risk-vault\/emergency-payout-failure/i),
  ).toBeVisible();
});
