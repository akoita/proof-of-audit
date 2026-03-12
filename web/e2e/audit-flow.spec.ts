import { expect, test } from "@playwright/test";

const apiBaseUrl = process.env.E2E_API_URL ?? "http://127.0.0.1:18080";

test("main audit flow works from submit through resolution", async ({
  page,
  request,
}) => {
  await page.goto("/");

  await expect(page.getByText("Pick a live contract to drive the audit flow")).toBeVisible();
  await page.getByRole("button", { name: /Vulnerable Bank/i }).click();
  await page.getByRole("button", { name: "Run audit" }).click();

  await expect(page.getByTestId("current-audit-status")).toHaveText("draft");
  await expect(
    page.getByRole("heading", {
      name: /Withdraw updates balance after the external call/i,
    }),
  ).toBeVisible();

  await page.getByRole("button", { name: "Publish stake" }).click();
  await expect(page.getByTestId("current-audit-status")).toHaveText("published");
  await expect(page.getByText("Published on-chain").first()).toBeVisible();

  await page.getByRole("button", { name: "Challenge with PoC" }).click();
  await expect(page.getByTestId("current-audit-status")).toHaveText("challenged");
  await expect(page.getByTestId("challenge-status")).toHaveText("opened");

  const auditsResponse = await request.get(`${apiBaseUrl}/audits`);
  expect(auditsResponse.ok()).toBeTruthy();
  const auditsPayload = (await auditsResponse.json()) as {
    items: Array<{ id: string }>;
  };
  const auditId = auditsPayload.items[0]?.id;
  expect(auditId).toBeTruthy();

  const resolveResponse = await request.post(`${apiBaseUrl}/audits/${auditId}/resolve`, {
    data: {
      upheld: true,
      resolved_by: "e2e-arbiter",
    },
  });
  expect(resolveResponse.ok()).toBeTruthy();

  await page.reload();
  await expect(page.getByTestId("current-audit-status")).toHaveText("resolved");
  await expect(page.getByTestId("challenge-status")).toHaveText("upheld");
  await expect(page.getByText(/Resolution upheld by e2e-arbiter/i)).toBeVisible();
});
