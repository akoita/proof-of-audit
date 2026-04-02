import path from "path";

import { expect, Page, test } from "@playwright/test";

async function openWorkbench(page: Page) {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Audit Workbench" })).toBeVisible();
  await expect(page.getByRole("heading", { name: /Demo Fixtures/i })).toBeVisible();
}

test("web app resolves the API base URL from runtime config", async ({ page }) => {
  const runtimeApiBaseUrl = "http://127.0.0.1:65501";
  const runtimeRequests: string[] = [];

  const auditorService = {
    service_id: "auditor-local",
    name: "Proof-of-Audit Auditor",
    manifest_schema: "proof-of-audit/v1",
    manifest_hash: "sha256:manifest",
    registration_kind: "local",
    registration_type: "service",
    registration_endpoint: "https://auditor.example.com",
    registration_uri: "ipfs://auditor-service",
    agent_id: 1,
    agent_registry: "0x0000000000000000000000000000000000000001",
    identity_source: "local",
    capability: "deterministic-audit",
    discovery_path: "/discover",
    submit_path: "/audits",
    execution_mode: "deterministic",
    execution_endpoint: "https://auditor.example.com/run",
    publish_path_template: "/audits/{id}/publish",
    challenge_path_template: "/audits/{id}/challenge",
    network: "anvil-e2e",
    active: true,
    supported_trust: ["deterministic"],
    settlement_mode: "manual",
    publication_mode: "onchain",
    staking_adapter_kind: "native",
    staking_adapter_address: "0x0000000000000000000000000000000000000002",
    staking_adapter_method: "stake",
    publication_scope: "public",
    registry_contract_address: "0x0000000000000000000000000000000000000003",
    validation_registry_address: "0x0000000000000000000000000000000000000004",
    validation_source: "local",
    validation_request_path_template: "/validation/{id}/request",
    validation_response_path_template: "/validation/{id}/response",
    reputation_registry_address: "0x0000000000000000000000000000000000000005",
    reputation_source: "local",
    reputation_path_template: "/reputation/{id}",
    submission_modes: ["demo_fixture", "deployed_address", "source_bundle"],
    resolution_modes: ["manual"],
    deterministic_resolution_supported: true,
    manual_fallback_supported: true,
    reputation: {
      score: 80,
      band: "trusted",
      resolved_challenge_count: 3,
      challenge_rejected_count: 2,
      challenge_upheld_count: 1,
      open_challenge_count: 0,
      published_claim_count: 4,
      draft_claim_count: 1,
      last_resolved_at: "2026-03-22T10:00:00Z",
      formula: "weighted-v1",
    },
  };

  const configPayload = {
    network: "anvil-e2e",
    chain_id: 31337,
    contract_address: "0x0000000000000000000000000000000000000006",
    explorer_base_url: "http://127.0.0.1:8545",
    arbiter: "0x0000000000000000000000000000000000000007",
    auditor: {
      id: "proof-of-audit-auditor",
      name: "Proof-of-Audit Auditor",
      version: "0.1.0",
      manifest_schema: "proof-of-audit/v1",
      service_type: "deterministic-auditor",
      description: "Deterministic smart contract auditor",
      capabilities: ["deterministic-audit"],
      operator: "Proof-of-Audit",
      resolution_policy: "manual fallback",
      reputation: auditorService.reputation,
    },
    auditor_service: auditorService,
    required_stake_wei: 10_000_000_000_000_000,
    required_challenge_bond_wei: 5_000_000_000_000_000,
    challenge_window_seconds: 86_400,
    deployment_ready: true,
  };

  await page.route("**/api/runtime-config", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ apiBaseUrl: runtimeApiBaseUrl }),
    });
  });

  await page.route("http://127.0.0.1:18081/**", async (route) => {
    throw new Error(`unexpected request to baked API origin: ${route.request().url()}`);
  });

  await page.route(`${runtimeApiBaseUrl}/**`, async (route) => {
    const url = new URL(route.request().url());
    runtimeRequests.push(url.pathname);

    if (url.pathname === "/audits") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ items: [] }),
      });
      return;
    }

    if (url.pathname === "/fixtures") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          items: [
            {
              id: "clean-vault",
              label: "Clean Vault",
              contract_name: "CleanVault",
              entry_contract: "CleanVault",
              benchmark_id: "clean-vault",
              address: "0x0000000000000000000000000000000000000010",
              challenge_proof_uri: "ipfs://clean-vault-proof",
              note: "Reference fixture",
              source_path: "demo/contracts/CleanVault.sol",
            },
          ],
        }),
      });
      return;
    }

    if (url.pathname === "/config") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(configPayload),
      });
      return;
    }

    if (url.pathname === "/auditor") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(auditorService),
      });
      return;
    }

    if (url.pathname === "/auditors") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ items: [auditorService] }),
      });
      return;
    }

    if (url.pathname === "/diagnostics/runtime") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          worker_runtime_mode: "deterministic",
          live_analysis_enabled: false,
          live_analysis_backend: "disabled",
          hosted_agent_forge_configured: false,
          hosted_agent_forge_url: null,
          explorer_api_url_configured: true,
          explorer_api_key_configured: false,
          source_bundle_storage_kind: "local",
          hosted_source_storage_compatible: true,
          allow_deployed_address_deterministic_fallback: true,
          warnings: [],
        }),
      });
      return;
    }

    throw new Error(`unexpected runtime API request: ${route.request().url()}`);
  });

  await openWorkbench(page);

  expect(runtimeRequests).toEqual(
    expect.arrayContaining(["/audits", "/fixtures", "/config", "/auditor", "/auditors"]),
  );
});

test("workbench shows loading copy instead of unavailable placeholders before hydration completes", async ({ page }) => {
  const runtimeApiBaseUrl = "http://127.0.0.1:65502";
  let releaseBootRequests: (() => void) | null = null;
  const bootRequestsReleased = new Promise<void>((resolve) => {
    releaseBootRequests = resolve;
  });

  const auditorService = {
    service_id: "auditor-local",
    name: "Proof-of-Audit Auditor",
    manifest_schema: "proof-of-audit/v1",
    manifest_hash: "sha256:manifest",
    registration_kind: "local",
    registration_type: "service",
    registration_endpoint: "https://auditor.example.com",
    registration_uri: "ipfs://auditor-service",
    capability: "deterministic-audit",
    discovery_path: "/discover",
    submit_path: "/audits",
    execution_mode: "deterministic",
    execution_endpoint: "https://auditor.example.com/run",
    publish_path_template: "/audits/{id}/publish",
    challenge_path_template: "/audits/{id}/challenge",
    network: "anvil-e2e",
    active: true,
    supported_trust: ["deterministic"],
    settlement_mode: "manual",
    publication_mode: "onchain",
    staking_adapter_kind: "native",
    publication_scope: "public",
    validation_request_path_template: "/validation/{id}/request",
    validation_response_path_template: "/validation/{id}/response",
    reputation_path_template: "/reputation/{id}",
    submission_modes: ["demo_fixture", "deployed_address", "source_bundle"],
    resolution_modes: ["manual"],
    deterministic_resolution_supported: true,
    manual_fallback_supported: true,
  };

  await page.route("**/api/runtime-config", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ apiBaseUrl: runtimeApiBaseUrl }),
    });
  });

  await page.route(`${runtimeApiBaseUrl}/**`, async (route) => {
    await bootRequestsReleased;
    const url = new URL(route.request().url());

    if (url.pathname === "/audits" || url.pathname === "/fixtures") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ items: [] }),
      });
      return;
    }

    if (url.pathname === "/config") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          network: "base-sepolia",
          chain_id: 84532,
          contract_address: "0x0000000000000000000000000000000000000006",
          explorer_base_url: "https://sepolia.basescan.org",
          arbiter: "0x0000000000000000000000000000000000000007",
          auditor: {
            id: "proof-of-audit-auditor",
            name: "Proof-of-Audit Auditor",
            version: "0.1.0",
            manifest_schema: "proof-of-audit/v1",
            service_type: "deterministic-auditor",
            description: "Deterministic smart contract auditor",
            capabilities: ["deterministic-audit"],
            operator: "Proof-of-Audit",
            resolution_policy: "manual fallback",
          },
          auditor_service: auditorService,
          required_stake_wei: 10_000_000_000_000_000,
          required_challenge_bond_wei: 5_000_000_000_000_000,
          challenge_window_seconds: 86_400,
          deployment_ready: true,
        }),
      });
      return;
    }

    if (url.pathname === "/auditor") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(auditorService),
      });
      return;
    }

    if (url.pathname === "/auditors") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ items: [auditorService] }),
      });
      return;
    }

    if (url.pathname === "/diagnostics/runtime") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          worker_runtime_mode: "deterministic",
          live_analysis_enabled: false,
          live_analysis_backend: "disabled",
          hosted_agent_forge_configured: false,
          hosted_agent_forge_url: null,
          explorer_api_url_configured: true,
          explorer_api_key_configured: false,
          source_bundle_storage_kind: "local",
          hosted_source_storage_compatible: true,
          allow_deployed_address_deterministic_fallback: true,
          warnings: [],
        }),
      });
      return;
    }

    throw new Error(`unexpected runtime API request: ${route.request().url()}`);
  });

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Audit Workbench" })).toBeVisible();
  await expect(page.getByText("Loading auditor services...")).toBeVisible();
  await expect(page.getByText("Loading network...")).toBeVisible();
  await expect(page.getByText("No auditor services are currently available.")).toHaveCount(0);
  await expect(page.getByText("Network unavailable")).toHaveCount(0);

  releaseBootRequests?.();

  await expect(page.getByText("Proof-of-Audit Auditor").first()).toBeVisible();
  await expect(page.getByText("base-sepolia · Chain 84532")).toBeVisible();
  await expect(page.getByText("Loading auditor services...")).toHaveCount(0);
});

test("connect wallet uses an injected provider and renders the connected account", async ({ page }) => {
  await page.addInitScript(() => {
    const listeners = new Map<string, Set<(...args: unknown[]) => void>>();
    const walletState = {
      accounts: [] as string[],
      chainId: "0x7a69",
    };

    const emit = (event: string, payload: unknown) => {
      for (const listener of listeners.get(event) ?? []) {
        listener(payload);
      }
    };

    Object.defineProperty(window, "ethereum", {
      configurable: true,
      value: {
        request: async ({ method, params }: { method: string; params?: Array<{ chainId?: string }> }) => {
          switch (method) {
            case "eth_accounts":
              return [...walletState.accounts];
            case "eth_chainId":
              return walletState.chainId;
            case "eth_requestAccounts":
              walletState.accounts = ["0x1111111111111111111111111111111111111111"];
              emit("accountsChanged", [...walletState.accounts]);
              return [...walletState.accounts];
            case "wallet_switchEthereumChain": {
              const nextChainId = params?.[0]?.chainId ?? walletState.chainId;
              walletState.chainId = nextChainId;
              emit("chainChanged", walletState.chainId);
              return null;
            }
            default:
              throw new Error(`unsupported wallet method: ${method}`);
          }
        },
        on: (event: string, listener: (...args: unknown[]) => void) => {
          if (!listeners.has(event)) {
            listeners.set(event, new Set());
          }
          listeners.get(event)?.add(listener);
        },
        removeListener: (event: string, listener: (...args: unknown[]) => void) => {
          listeners.get(event)?.delete(listener);
        },
      },
    });
  });

  await openWorkbench(page);
  await page.getByTestId("connect-wallet-btn").click();

  await expect(page.getByTestId("wallet-address-chip")).toContainText("0x111111...111111");
  await expect(page.getByTestId("wallet-address-chip")).toContainText("Chain 31337");
});

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
  await expect(page.getByText(/Plain proof-URI challenges require manual review/i)).toBeVisible();

  await page.getByRole("button", { name: /Disputed/i }).click();
  await expect(page.getByRole("heading", { name: /Verifier Dossier/i })).toBeVisible();
  await expect(page.getByText(/Machine-Readable Dossier/i)).toBeVisible();
  await expect(page.getByText(/STRUCTURED CLAIM/i)).toBeVisible();
});

test("source bundle mode can submit without a deployed address", async ({ page }) => {
  await openWorkbench(page);

  const submitButton = page.getByTestId("submit-audit");
  await page.getByTestId("submission-mode-source_bundle").click();
  await expect(submitButton).toBeDisabled();

  await page
    .getByTestId("source-bundle-uri")
    .fill("https://example.com/bundles/reentrancy-bank.zip");
  await expect(submitButton).toBeEnabled();

  await submitButton.click();
  await expect(page.getByTestId("current-audit-status")).toHaveText("draft");
  await expect(page.getByTestId("publish-btn")).toBeDisabled();
  await expect(
    page.getByText(/must be deployed and resubmitted as a deployed address/i),
  ).toBeVisible();
});

test("source bundle mode accepts a local Solidity file upload", async ({ page }) => {
  await openWorkbench(page);

  const submitButton = page.getByTestId("submit-audit");
  await page.getByTestId("submission-mode-source_bundle").click();
  await expect(submitButton).toBeDisabled();

  await page.getByTestId("source-bundle-file-input").setInputFiles(
    path.join(process.cwd(), "..", "demo", "contracts", "UncheckedTreasury.sol"),
  );

  await expect(page.getByTestId("source-bundle-uri")).not.toHaveValue("");
  await expect(submitButton).toBeEnabled();
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
