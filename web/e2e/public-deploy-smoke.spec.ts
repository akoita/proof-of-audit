import { expect, test } from "@playwright/test";

test("public deployment hydrates into a loaded workbench state", async ({ page, baseURL }) => {
  test.skip(!baseURL, "E2E_WEB_URL must point at the deployed public web app.");

  const runtimeResponses: string[] = [];
  page.on("response", (response) => {
    const url = response.url();
    if (
      url.includes("/api/runtime-config")
      || url.includes("/config")
      || url.includes("/auditor")
      || url.includes("/auditors")
      || url.includes("/audits")
    ) {
      runtimeResponses.push(`${response.status()} ${url}`);
    }
  });

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Audit Workbench" })).toBeVisible();
  await expect(page.getByText("Loading workspace")).toHaveCount(0, { timeout: 30_000 });
  await expect(page.getByText("Network unavailable")).toHaveCount(0);
  await expect(page.getByText("No auditor services are currently available.")).toHaveCount(0);
  await expect(page.locator("[data-testid='auditor-service-select'] option")).toHaveCount(1);
  await expect(page.getByText(/Chain \d+/)).toBeVisible();

  expect(runtimeResponses).toEqual(
    expect.arrayContaining([
      expect.stringMatching(/^200 .*\/api\/runtime-config$/),
      expect.stringMatching(/^200 .*\/config$/),
      expect.stringMatching(/^200 .*\/auditor$/),
      expect.stringMatching(/^200 .*\/auditors$/),
      expect.stringMatching(/^200 .*\/audits$/),
    ]),
  );
});
