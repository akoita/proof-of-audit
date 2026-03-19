import { expect, Locator, Page, test } from "@playwright/test";

async function createAuditFromFixture(page: Page, fixtureName: RegExp) {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Audit Workbench" })).toBeVisible();
  await expect(page.getByRole("heading", { name: /Demo Fixtures/i })).toBeVisible();
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

test("clean fixture challenge stays open for manual review", async ({ page }) => {
  await createAuditFromFixture(page, /Clean Vault/i);

  await expect(
    page.getByText(/No benchmark issue found across the supported checks/i).first(),
  ).toBeVisible();
  await expect(page.getByText("Target Comparison", { exact: true })).toBeVisible();

  await publishActiveAudit(page);
  await page.getByTestId("challenge-btn").click();

  await expect(page.getByTestId("current-audit-status")).toHaveText("challenged");
  await expect(page.getByText("Challenge & Resolution", { exact: true })).toBeVisible();
  await expect(page.getByText("OPENED", { exact: true })).toBeVisible();
  await expect(page.getByText("Manual Fallback", { exact: true })).toBeVisible();
  await expect(page.getByText(/Plain proof-URI challenges require manual review/i)).toBeVisible();
  await expect(
    page.getByText(/deterministic benchmark verifier has been retired/i),
  ).toBeVisible();
});

test("plain proof URI challenge evidence stays open for manual review", async ({ page }) => {
  await createAuditFromFixture(page, /Clean Vault/i);
  await publishActiveAudit(page);

  await challengeInput(page).fill("ipfs://wrong-proof");
  await page.getByTestId("challenge-btn").click();

  await expect(page.getByTestId("current-audit-status")).toHaveText("challenged");
  await expect(page.getByText("OPENED", { exact: true })).toBeVisible();
  await expect(page.getByText("Manual Fallback", { exact: true })).toBeVisible();
  await expect(
    page.getByText(/Plain proof-URI challenges require manual review/i),
  ).toBeVisible();
  await expect(
    page.getByText(/ipfs:\/\/wrong-proof/i),
  ).toBeVisible();
});

test("dual risk vault renders the richer multi-finding report", async ({ page }) => {
  await createAuditFromFixture(page, /Dual Risk Vault/i);

  await expect(page.getByText("Findings", { exact: true })).toBeVisible();
  await expect(page.getByText("Missing access control on rotateOwner()")).toBeVisible();
  await expect(page.getByText("Unchecked external call in emergencyPayout()")).toBeVisible();
  await page.getByRole("button", { name: /Missing access control on rotateOwner\(\)/i }).click();
  await page.getByRole("button", { name: /Unchecked external call in emergencyPayout\(\)/i }).click();
  await expect(page.getByText(/Access Control · High confidence · rotateOwner\(address\)/i)).toBeVisible();
  await expect(page.getByText(/Unchecked External Call · Medium confidence · emergencyPayout\(uint256\)/i)).toBeVisible();
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
  const initialComparisonCount = await page.locator(".related-claim-card").count();
  await page.getByTestId("submit-audit").click();

  await expect(page.getByText("Target Comparison", { exact: true })).toBeVisible();
  await expect
    .poll(async () => page.locator(".related-claim-card").count())
    .toBeGreaterThanOrEqual(initialComparisonCount + 1);
  await expect(page.getByText(/published/i)).toBeVisible();
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

test("archive view excludes live published claims", async ({ page }) => {
  await createAuditFromFixture(page, /Dual Risk Vault/i);
  await publishActiveAudit(page);

  await page.getByRole("button", { name: /Reentrancy Bank/i }).click();
  await page.getByTestId("submit-audit").click();
  await publishActiveAudit(page);
  await page.getByTestId("challenge-btn").click();
  await expect(page.getByTestId("current-audit-status")).toHaveText("challenged");

  const sidebarNav = page.locator(".sidebar-nav");
  await sidebarNav.getByRole("button", { name: "Archive" }).click();

  await expect(page.getByText("Audit History Archive", { exact: true })).toBeVisible();
  await expect(page.getByText("No archived audits", { exact: true })).toBeVisible();
  await expect(
    page.getByText(/The vault exposes both unrestricted role rotation and unchecked emergency payouts/i),
  ).toHaveCount(0);
});

test("redesigned dashboards only show real state or explicit unavailable labels", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("System Healthy", { exact: true })).toHaveCount(0);
  await expect(page.getByText(/AUTO-SAVE:/i)).toHaveCount(0);
  await expect(page.getByText(/Nodes: 12 Active/i)).toHaveCount(0);
  await expect(page.getByText(/Block: 18,241,002/i)).toHaveCount(0);
  await expect(page.getByText(/Audits:/i)).toBeVisible();
  await expect(page.getByText(/Fixtures:/i)).toBeVisible();

  await createAuditFromFixture(page, /Clean Vault/i);
  await publishActiveAudit(page);

  const sidebarNav = page.locator(".sidebar-nav");
  await sidebarNav.getByRole("button", { name: "Published" }).click();
  await expect(page.getByText("Not opened yet", { exact: true })).toBeVisible();
  await expect(page.getByText(/Deterministic Verifier L2/i)).toHaveCount(0);
  await expect(page.getByText(/FORENSIC SYNC: 100%/i)).toHaveCount(0);

  await sidebarNav.getByRole("button", { name: "Workbench" }).click();
  await challengeInput(page).fill("ipfs://wrong-proof");
  await page.getByTestId("challenge-btn").click();
  await expect(page.getByTestId("current-audit-status")).toHaveText("challenged");

  await sidebarNav.getByRole("button", { name: "Disputed" }).click();
  await expect(page.getByText("Manual Fallback", { exact: true })).toBeVisible();
  await expect(page.getByText(/ZKP Verifier Active/i)).toHaveCount(0);
  await expect(page.getByText(/Mainnet Ethereum/i)).toHaveCount(0);

  await sidebarNav.getByRole("button", { name: "Reputation" }).click();
  await expect(page.getByText(/Identity:/i)).toBeVisible();
  await expect(page.getByText(/Validation:/i)).toBeVisible();
  await expect(page.getByText(/WorldID Identity/i)).toHaveCount(0);
  await expect(page.getByText(/GitHub Activity/i)).toHaveCount(0);
  await expect(page.getByText(/Top 0.1% Globally/i)).toHaveCount(0);
  await expect(page.getByText(/NETWORK PULSE: Healthy & Synced/i)).toHaveCount(0);
});

test("redesigned controls are wired to real links and stateful actions", async ({ page }) => {
  await page.goto("/");
  const sidebarNav = page.locator(".sidebar-nav");

  await page.getByRole("button", { name: /Technical Docs/i }).click();
  await expect(page.getByRole("heading", { name: /Proof-of-Audit Documentation/i })).toBeVisible();
  await sidebarNav.getByRole("button", { name: "Workbench" }).click();

  await expect(page.getByRole("link", { name: /Support/i })).toHaveAttribute(
    "href",
    "https://github.com/akoita/proof-of-audit/issues",
  );

  await createAuditFromFixture(page, /Dual Risk Vault/i);
  await publishActiveAudit(page);

  await sidebarNav.getByRole("button", { name: "Published" }).click();

  await page.getByRole("button", { name: "Code Audit" }).click();
  await expect(page.getByText("REPORT HASH", { exact: true })).toBeVisible();
  await expect(page.getByText("SUPPORTED CHECKS", { exact: true })).toBeVisible();

  const publishedCopy = page.getByRole("button", { name: "Copy published transaction hash" });
  await publishedCopy.click();
  await expect(publishedCopy).toHaveText("Copied");

  await sidebarNav.getByRole("button", { name: "Workbench" }).click();
  await challengeInput(page).fill("ipfs://wrong-proof");
  await page.getByTestId("challenge-btn").click();
  await expect(page.getByTestId("current-audit-status")).toHaveText("challenged");

  await sidebarNav.getByRole("button", { name: "Disputed" }).click();
  await expect(page.getByRole("link", { name: /View Evidence/i })).toHaveAttribute("href", "ipfs://wrong-proof");
  await expect(page.getByText(/^Report /)).toBeVisible();

  const disputedCopy = page.getByRole("button", { name: "Copy disputed transaction hash" });
  await disputedCopy.click();
  await expect(disputedCopy).toHaveText("Copied");
});
