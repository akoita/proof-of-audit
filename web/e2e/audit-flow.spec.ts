import { expect, test } from "@playwright/test";

test("main audit flow works from submit through resolution", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByText("Pick a live contract to drive the audit flow")).toBeVisible();
  await page.getByRole("button", { name: /Clean Vault/i }).click();
  await page.getByRole("button", { name: "Run audit" }).click();

  await expect(page.getByTestId("current-audit-status")).toHaveText("draft");
  await expect(
    page.getByRole("heading", {
      name: /No benchmark issue found across the supported checks/i,
    }),
  ).toBeVisible();

  await page.getByRole("button", { name: "Publish stake" }).click();
  await expect(page.getByTestId("current-audit-status")).toHaveText("published");
  await expect(page.getByText("Published on-chain").first()).toBeVisible();

  await page.getByRole("button", { name: "Challenge with PoC" }).click();
  await expect(page.getByTestId("current-audit-status")).toHaveText("resolved");
  await expect(page.getByTestId("challenge-status")).toHaveText("upheld");
  await expect(page.getByText(/Resolution upheld by deterministic-verifier/i)).toBeVisible();
  await expect(page.getByText(/verified: The submitted PoC demonstrates a missed issue/i)).toBeVisible();
});
