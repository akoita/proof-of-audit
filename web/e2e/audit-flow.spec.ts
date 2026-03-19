import { expect, Locator, Page, test } from "@playwright/test";

async function createAuditFromFixture(page: Page, fixtureName: RegExp) {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Audit Workbench" })).toBeVisible();
  await expect(page.getByText("Demo fixtures", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: fixtureName }).click();
  await page.getByTestId("submit-audit").click();
  await expect(page.getByTestId("current-audit-status")).toHaveText("draft");
  await expect(page.getByText("Detailed Analysis Findings", { exact: true })).toBeVisible();
}

async function publishActiveAudit(page: Page) {
  await page.getByTestId("publish-btn").click();
  await expect(page.getByTestId("current-audit-status")).toHaveText("published");
}

function challengeInput(page: Page): Locator {
  return page.getByPlaceholder("ipfs://proof-uri...");
}

test("clean fixture challenge auto-resolves upheld", async ({ page }) => {
  await createAuditFromFixture(page, /Clean Vault/i);

  await expect(
    page.getByText(/No benchmark issue found across the supported checks/i).first(),
  ).toBeVisible();
  await expect(page.getByText("Evidence Verification Hashes", { exact: true })).toBeVisible();

  await publishActiveAudit(page);
  await page.getByTestId("challenge-btn").click();

  await expect(page.getByTestId("current-audit-status")).toHaveText("resolved");
  await expect(page.getByTestId("challenge-status")).toHaveText("upheld");
  await expect(page.getByText("Deterministic", { exact: true })).toBeVisible();
  await expect(page.getByText(/Resolution upheld by deterministic-verifier/i)).toBeVisible();
  await expect(
    page.getByText(/verified: The submitted PoC demonstrates a missed issue/i),
  ).toBeVisible();
});

test("invalid challenge evidence stays open for manual review", async ({ page }) => {
  await createAuditFromFixture(page, /Clean Vault/i);
  await publishActiveAudit(page);

  await challengeInput(page).fill("ipfs://wrong-proof");
  await page.getByTestId("challenge-btn").click();

  await expect(page.getByTestId("current-audit-status")).toHaveText("challenged");
  await expect(page.getByTestId("challenge-status")).toHaveText("opened");
  await expect(page.getByText("Manual Fallback", { exact: true })).toBeVisible();
  await expect(
    page.getByText(/invalid_evidence: The submitted PoC does not match/i),
  ).toBeVisible();
  await expect(
    page.getByText(/Provide the curated artifact ipfs:\/\/clean-vault\/missed-reentrancy/i),
  ).toBeVisible();
});

test("dual risk vault renders the richer multi-finding report", async ({ page }) => {
  await createAuditFromFixture(page, /Dual Risk Vault/i);

  await expect(page.getByText("Detailed Analysis Findings", { exact: true })).toBeVisible();
  await expect(page.getByText("Findings", { exact: true })).toBeVisible();
  await expect(page.getByText("Missing access control on rotateOwner()")).toBeVisible();
  await expect(page.getByText("Unchecked external call in emergencyPayout()")).toBeVisible();
  await expect(page.getByText(/Access Control · High confidence · rotateOwner\(address\)/i)).toBeVisible();
  await expect(
    page.getByText(/Unchecked External Call · Medium confidence · emergencyPayout\(uint256\)/i),
  ).toBeVisible();
  await expect(
    page.getByText(/Ownership can be reassigned by any caller without authorization/i),
  ).toBeVisible();
  await expect(
    page.getByText(/The emergency payout path ignores the success flag from a low-level call/i),
  ).toBeVisible();
  await expect(
    page.getByText(/An attacker can seize control of privileged payout operations/i),
  ).toBeVisible();
  await expect(
    page.getByText(/Restrict ownership changes to the current owner or a governed admin path/i),
  ).toBeVisible();
  await expect(
    page.getByText(/Source: demo\/contracts\/DualRiskVault\.sol:15-17/i),
  ).toBeVisible();
  await expect(page.getByText(/Evidence: ipfs:\/\/dual-risk-vault\/owner-takeover/i)).toBeVisible();
  await expect(
    page.getByText(/Evidence: ipfs:\/\/dual-risk-vault\/emergency-payout-failure/i),
  ).toBeVisible();
});

test("target comparison groups multiple claims for one contract", async ({ page }) => {
  await createAuditFromFixture(page, /Clean Vault/i);
  const initialComparisonCount = await page.locator(".comparison-item").count();
  await page.getByTestId("submit-audit").click();

  await expect(page.getByText("Target comparison", { exact: true })).toBeVisible();
  await expect
    .poll(async () => page.locator(".comparison-item").count())
    .toBeGreaterThanOrEqual(initialComparisonCount + 1);
  await expect(page.getByText(/published · .*challenged · .*resolved/i)).toBeVisible();
});

test("source bundle mode can submit without a deployed address", async ({ page }) => {
  await page.goto("/");

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

test("filtered lifecycle views do not reuse stale draft selections", async ({ page }) => {
  await createAuditFromFixture(page, /Clean Vault/i);
  await publishActiveAudit(page);

  await page.getByRole("button", { name: /Reentrancy Bank/i }).click();
  await page.getByTestId("submit-audit").click();
  await publishActiveAudit(page);
  await challengeInput(page).fill("ipfs://wrong-proof");
  await page.getByTestId("challenge-btn").click();
  await expect(page.getByTestId("current-audit-status")).toHaveText("challenged");

  await page.getByRole("button", { name: /Dual Risk Vault/i }).click();
  await page.getByTestId("submit-audit").click();
  await expect(page.getByTestId("current-audit-status")).toHaveText("draft");
  await expect(
    page.getByText(/The vault exposes both unrestricted role rotation and unchecked emergency payouts/i),
  ).toBeVisible();

  const sidebarNav = page.locator(".sidebar-nav");

  await sidebarNav.getByRole("button", { name: "Published" }).click();
  await expect(page.getByText("SECURITY AUDIT: PUBLISHED", { exact: true })).toBeVisible();
  await expect(page.getByText("TOTAL COMMITMENT STAKE", { exact: true })).toBeVisible();
  await expect(
    page.getByText(/The vault exposes both unrestricted role rotation and unchecked emergency payouts/i),
  ).toHaveCount(0);

  await sidebarNav.getByRole("button", { name: "Disputed" }).click();
  await expect(page.getByText("Active Challenges", { exact: true })).toBeVisible();
  await expect(
    page.getByText(/The vault exposes both unrestricted role rotation and unchecked emergency payouts/i),
  ).toHaveCount(0);
});
