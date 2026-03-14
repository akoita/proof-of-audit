"use client";

import { FormEvent, useEffect, useState, useTransition } from "react";

type Finding = {
  finding_id: string;
  title: string;
  severity: string;
  category: string;
  description: string;
  impact: string;
  recommendation: string;
  detector: string;
  confidence: string;
  affected_function?: string | null;
  source_path?: string | null;
  start_line?: number | null;
  end_line?: number | null;
  evidence_uri?: string | null;
};

type AuditorProfile = {
  id: string;
  name: string;
  version: string;
  manifest_schema: string;
  service_type: string;
  description: string;
  capabilities: string[];
  operator: string;
  resolution_policy: string;
};

type AuditorServiceRecord = {
  service_id: string;
  name: string;
  manifest_schema: string;
  manifest_hash: string;
  registration_kind: string;
  registration_uri: string;
  capability: string;
  discovery_path: string;
  submit_path: string;
  publish_path_template: string;
  challenge_path_template: string;
  network: string;
  registry_contract_address?: string | null;
};

type PublicContractConfig = {
  network: string;
  chain_id: number;
  contract_address: string | null;
  explorer_base_url: string;
  arbiter: string | null;
  auditor: AuditorProfile;
  auditor_service: AuditorServiceRecord;
  required_stake_wei: number;
  required_challenge_bond_wei: number;
  challenge_window_seconds: number;
  deployment_ready: boolean;
};

type InputKind =
  | "deployed_address"
  | "demo_fixture"
  | "source_bundle"
  | "repository_url";

type Submission = {
  input_kind: InputKind;
  chain_id?: number | null;
  contract_address?: string | null;
  fixture_id?: string | null;
  entry_contract?: string | null;
  source_bundle_uri?: string | null;
  source_bundle_label?: string | null;
  repository_url?: string | null;
};

type AuditRecord = {
  id: string;
  contract_address: string;
  agent: AuditorProfile;
  submission: Submission;
  submitted_by: string;
  status: string;
  created_at: string;
  report: {
    benchmark_id: string;
    contract_address: string;
    summary: string;
    findings: Finding[];
    supported_checks: string[];
    confidence: string;
    report_hash: string;
    metadata_hash: string;
    max_severity: number;
    finding_count: number;
    severity_breakdown: Record<string, number>;
  };
  onchain: null | {
    audit_id?: number;
    network: string;
    chain_id: number;
    contract_address?: string | null;
    explorer_base_url: string;
    agent_identity: string;
    agent_name?: string | null;
    agent_version?: string | null;
    stake_wei: number;
    report_hash: string;
    metadata_hash: string;
    max_severity: number;
    finding_count: number;
    publish_tx_hash: string;
    publish_tx_url?: string | null;
  };
  challenge: null | {
    challenger: string;
    challenger_address?: string | null;
    proof_uri: string;
    submitted_at: string;
    verifier: string;
    status: string;
    resolution_path: string;
    verification_status?: string | null;
    verification_summary?: string | null;
    verification_detail?: string | null;
    verification_case_id?: string | null;
    resolution?: string | null;
    resolved_at?: string | null;
    resolved_by?: string | null;
    beneficiary_address?: string | null;
    payout_wei?: number | null;
    challenge_hash?: string | null;
    challenge_bond_wei?: number | null;
    chain_id?: number | null;
    challenge_tx_hash: string;
    challenge_tx_url?: string | null;
    resolve_tx_hash?: string | null;
    resolve_tx_url?: string | null;
  };
};

type DemoFixture = {
  id: string;
  label: string;
  contract_name: string;
  entry_contract: string;
  benchmark_id: string;
  address: string;
  challenge_proof_uri: string;
  note: string;
  source_path: string;
};

const API_BASE_URL =
  process.env.NEXT_PUBLIC_PROOF_OF_AUDIT_API_URL ?? "http://127.0.0.1:8080";

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });

  const payload = (await response.json()) as T & {
    error?: string;
    message?: string;
  };

  if (!response.ok) {
    throw new Error(payload.message ?? payload.error ?? "Request failed");
  }

  return payload;
}

function formatEth(wei: number): string {
  return `${(wei / 1e18).toFixed(3)} ETH`;
}

function titleCase(value: string): string {
  return value
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatWindow(seconds: number): string {
  if (seconds % 86400 === 0) {
    return `${seconds / 86400} day`;
  }
  if (seconds % 3600 === 0) {
    return `${seconds / 3600} hr`;
  }
  return `${seconds}s`;
}

function shortenHex(value: string, start = 6, end = 4): string {
  if (value.length <= start + end + 3) {
    return value;
  }
  return `${value.slice(0, start)}...${value.slice(-end)}`;
}

function isExplorerLink(url: string | null | undefined): url is string {
  if (!url) {
    return false;
  }
  return !url.includes("127.0.0.1") && !url.includes("localhost");
}

function addressUrl(
  baseUrl: string | null | undefined,
  address: string | null | undefined,
) {
  if (!isExplorerLink(baseUrl) || !address) {
    return null;
  }
  return `${baseUrl}/address/${address}`;
}

function statusTone(status: string) {
  switch (status) {
    case "published":
      return "confirmed";
    case "resolved":
      return "confirmed";
    case "upheld":
      return "warning";
    case "rejected":
      return "confirmed";
    case "challenged":
      return "warning";
    case "opened":
      return "warning";
    case "draft":
      return "neutral";
    default:
      return "neutral";
  }
}

function lifecycleLabel(audit: AuditRecord) {
  if (audit.status === "resolved" && audit.challenge?.resolution) {
    return `Challenge ${audit.challenge.resolution}`;
  }
  if (audit.challenge) {
    return "Challenge opened on-chain";
  }
  if (audit.onchain) {
    return "Published on-chain";
  }
  return "Draft report prepared";
}

function suggestedProofUriForBenchmark(benchmarkId: string): string {
  switch (benchmarkId) {
    case "clean-vault":
      return "ipfs://clean-vault/missed-reentrancy";
    case "reentrancy-bank":
      return "ipfs://reentrancy-bank/withdraw-drain";
    case "admin-setter":
      return "ipfs://admin-setter/unauthorized-admin-change";
    case "dual-risk-vault":
      return "ipfs://dual-risk-vault/owner-takeover";
    case "unchecked-treasury":
      return "ipfs://unchecked-treasury/unchecked-call-failure";
    default:
      return "ipfs://benchmark-proof";
  }
}

function relativeTimeLabel(timestamp: string) {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) {
    return timestamp;
  }
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function submissionModeLabel(mode: InputKind): string {
  switch (mode) {
    case "demo_fixture":
      return "Demo fixture";
    case "source_bundle":
      return "Source bundle";
    case "repository_url":
      return "Repository";
    default:
      return "Deployed address";
  }
}

function agentVersionLabel(agent: AuditorProfile | null | undefined): string {
  if (!agent) {
    return "loading";
  }
  return `${agent.name} v${agent.version}`;
}

function submissionTargetLabel(audit: AuditRecord): string {
  if (audit.submission.input_kind === "demo_fixture") {
    return audit.submission.entry_contract ?? audit.submission.fixture_id ?? audit.report.benchmark_id;
  }
  if (audit.submission.input_kind === "source_bundle") {
    return (
      audit.submission.entry_contract ??
      audit.submission.source_bundle_label ??
      "source bundle"
    );
  }
  return shortenHex(audit.contract_address, 8, 6);
}

function preferredDemoFixture(fixtures: DemoFixture[]): DemoFixture | null {
  if (fixtures.length === 0) {
    return null;
  }
  return fixtures.find((fixture) => fixture.id === "clean-vault") ?? fixtures[0];
}

function challengePathLabel(audit: AuditRecord): string {
  if (!audit.challenge) {
    return "Deterministic path ready";
  }
  return audit.challenge.resolution_path === "deterministic"
    ? "Deterministic path"
    : "Manual fallback";
}

function challengePathSummary(audit: AuditRecord): string {
  if (!audit.challenge) {
    return "Curated fixture evidence auto-resolves known benchmark cases on-chain. Human review is only needed when the verifier cannot confirm the evidence.";
  }
  if (audit.challenge.resolution_path === "deterministic") {
    return "The verifier matched curated benchmark evidence and completed the on-chain resolution automatically.";
  }
  return "The verifier could not confirm a curated case, so the challenge remains on the manual fallback path.";
}

export function AuditWorkbench() {
  const [submissionMode, setSubmissionMode] = useState<InputKind>("demo_fixture");
  const [contractAddress, setContractAddress] = useState("");
  const [selectedFixtureId, setSelectedFixtureId] = useState("");
  const [entryContract, setEntryContract] = useState("");
  const [sourceBundleUri, setSourceBundleUri] = useState("");
  const [sourceBundleLabel, setSourceBundleLabel] = useState("");
  const [demoFixtures, setDemoFixtures] = useState<DemoFixture[]>([]);
  const [recentAudits, setRecentAudits] = useState<AuditRecord[]>([]);
  const [activeAudit, setActiveAudit] = useState<AuditRecord | null>(null);
  const [contractConfig, setContractConfig] = useState<PublicContractConfig | null>(
    null,
  );
  const [auditorService, setAuditorService] = useState<AuditorServiceRecord | null>(null);
  const [proofUri, setProofUri] = useState("ipfs://demo-poc");
  const [error, setError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isLoaded, setIsLoaded] = useState(false);
  const [activeAction, setActiveAction] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  const selectedFixture =
    demoFixtures.find((fixture) => fixture.id === selectedFixtureId) ??
    demoFixtures.find((fixture) => fixture.address === contractAddress) ??
    null;
  const publishStake = contractConfig?.required_stake_wei ?? 10_000_000_000_000_000;
  const challengeBond =
    contractConfig?.required_challenge_bond_wei ?? 5_000_000_000_000_000;

  useEffect(() => {
    startTransition(() => {
      void loadWorkbench();
    });
  }, []);

  async function loadWorkbench() {
    setLoadError(null);
    try {
      const [auditPayload, fixturePayload, configPayload, auditorPayload] = await Promise.all([
        apiFetch<{ items: AuditRecord[] }>("/audits"),
        apiFetch<{ items: DemoFixture[] }>("/fixtures"),
        apiFetch<PublicContractConfig>("/config"),
        apiFetch<AuditorServiceRecord>("/auditor"),
      ]);
      setRecentAudits(auditPayload.items);
      setDemoFixtures(fixturePayload.items);
      setContractConfig(configPayload);
      setAuditorService(auditorPayload);
      if (auditPayload.items.length > 0) {
        setActiveAudit((current) => current ?? auditPayload.items[0]);
      }
      if (fixturePayload.items.length > 0 && !selectedFixtureId) {
        const firstFixture = preferredDemoFixture(fixturePayload.items);
        if (!firstFixture) {
          return;
        }
        setSubmissionMode("demo_fixture");
        setSelectedFixtureId(firstFixture.id);
        setContractAddress(firstFixture.address);
        setEntryContract(firstFixture.entry_contract);
        setProofUri(firstFixture.challenge_proof_uri);
      }
    } catch (nextError) {
      setLoadError(
        nextError instanceof Error
          ? nextError.message
          : "Failed to load Proof-of-Audit workbench data",
      );
    } finally {
      setIsLoaded(true);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setActiveAction("Generating deterministic audit report");

    startTransition(() => {
      void (async () => {
        try {
          const payload =
            submissionMode === "demo_fixture"
              ? {
                  input_kind: "demo_fixture",
                  fixture_id: selectedFixtureId,
                  chain_id: contractConfig?.chain_id,
                  entry_contract: entryContract || selectedFixture?.entry_contract,
                  submitted_by: "web-demo",
                }
              : submissionMode === "source_bundle"
                ? {
                    input_kind: "source_bundle",
                    source_bundle_uri: sourceBundleUri,
                    source_bundle_label: sourceBundleLabel || undefined,
                    entry_contract: entryContract || undefined,
                    submitted_by: "web-demo",
                  }
                : {
                    input_kind: "deployed_address",
                    contract_address: contractAddress,
                    chain_id: contractConfig?.chain_id,
                    entry_contract: entryContract || undefined,
                    submitted_by: "web-demo",
                  };
          const created = await apiFetch<AuditRecord>("/audits", {
            method: "POST",
            body: JSON.stringify(payload),
          });
          syncAudit(created);
        } catch (submitError) {
          setError(
            submitError instanceof Error
              ? submitError.message
              : "Failed to create audit",
          );
        } finally {
          setActiveAction(null);
        }
      })();
    });
  }

  async function handlePublish() {
    if (!activeAudit) {
      return;
    }
    setError(null);
    setActiveAction("Submitting publish transaction");

    startTransition(() => {
      void (async () => {
        try {
          const published = await apiFetch<AuditRecord>(
            `/audits/${activeAudit.id}/publish`,
            {
              method: "POST",
              body: JSON.stringify({
                stake_wei: publishStake,
              }),
            },
          );
          syncAudit(published);
        } catch (publishError) {
          setError(
            publishError instanceof Error
              ? publishError.message
              : "Failed to publish audit",
          );
        } finally {
          setActiveAction(null);
        }
      })();
    });
  }

  async function handleChallenge() {
    if (!activeAudit) {
      return;
    }
    setError(null);
    setActiveAction("Opening challenge transaction");

    startTransition(() => {
      void (async () => {
        try {
          const challenged = await apiFetch<AuditRecord>(
            `/audits/${activeAudit.id}/challenge`,
            {
              method: "POST",
              body: JSON.stringify({
                proof_uri: proofUri,
                challenger: "whitehat-demo",
              }),
            },
          );
          syncAudit(challenged);
        } catch (challengeError) {
          setError(
            challengeError instanceof Error
              ? challengeError.message
              : "Failed to challenge audit",
          );
        } finally {
          setActiveAction(null);
        }
      })();
    });
  }

  function syncAudit(nextAudit: AuditRecord) {
    setActiveAudit(nextAudit);
    setSubmissionMode(nextAudit.submission.input_kind);
    setContractAddress(nextAudit.submission.contract_address ?? nextAudit.contract_address);
    setSelectedFixtureId(nextAudit.submission.fixture_id ?? "");
    setEntryContract(nextAudit.submission.entry_contract ?? "");
    setSourceBundleUri(nextAudit.submission.source_bundle_uri ?? "");
    setSourceBundleLabel(nextAudit.submission.source_bundle_label ?? "");
    setProofUri(suggestedProofUriForBenchmark(nextAudit.report.benchmark_id));
    setRecentAudits((current) =>
      [nextAudit, ...current.filter((audit) => audit.id !== nextAudit.id)].sort(
        (left, right) => right.created_at.localeCompare(left.created_at),
      ),
    );
  }

  return (
    <main className="page-shell">
      {/* ── Hero: compact headline + config sidebar ──────────── */}
      <section className="hero">
        <div className="hero-copy">
          <p className="eyebrow">Proof-of-Audit Workbench</p>
          <h1>Trust and challengeability for agent-made code judgments.</h1>
          <p className="lede">
            A named auditor agent makes a claim about a contract, stakes behind
            it, and can be challenged through a neutral on-chain process when
            that claim is disputed.
          </p>
        </div>
        <div className="signal-panel">
          <div className="panel-kicker">
            <span>Live demo configuration</span>
            <strong>{contractConfig?.network ?? "loading"}</strong>
          </div>
          <div className="signal-grid">
            <div className="signal-row">
              <span>Network</span>
              <strong>
                {contractConfig
                  ? `${contractConfig.network} · chain ${contractConfig.chain_id}`
                  : "Loading network configuration"}
              </strong>
            </div>
            <div className="signal-row">
              <span>Publish stake</span>
              <strong>{formatEth(publishStake)}</strong>
            </div>
            <div className="signal-row">
              <span>Challenge bond</span>
              <strong>{formatEth(challengeBond)}</strong>
            </div>
            <div className="signal-row">
              <span>Auditor</span>
              <strong>{agentVersionLabel(contractConfig?.auditor)}</strong>
            </div>
            <div className="signal-row">
              <span>Window</span>
              <strong>
                {contractConfig ? formatWindow(contractConfig.challenge_window_seconds) : "..."}
              </strong>
            </div>
          </div>
          <div className="signal-note">
            <span className="signal-note-label">Service discovery</span>
            <strong>{auditorService?.name ?? contractConfig?.auditor?.name ?? "loading"}</strong>
            <p className="muted">
              {auditorService
                ? `${auditorService.service_id} · ${titleCase(auditorService.capability)}`
                : contractConfig?.auditor
                  ? `${contractConfig.auditor.id} · ${titleCase(contractConfig.auditor.service_type)}`
                  : "Loading agent identity"}
            </p>
            <p className="muted">
              {contractConfig?.auditor?.description ??
                "Named auditor profile will appear here once config loads."}
            </p>
            {auditorService ? (
              <div className="inline-links">
                <span>{titleCase(auditorService.registration_kind)}</span>
                <span title={auditorService.manifest_hash}>
                  {shortenHex(auditorService.manifest_hash, 10, 8)}
                </span>
                <span title={auditorService.registration_uri}>
                  {shortenHex(auditorService.registration_uri, 28, 18)}
                </span>
                <span>{auditorService.discovery_path}</span>
                <span>{auditorService.submit_path}</span>
              </div>
            ) : null}
          </div>
          <div className="signal-note">
            {contractConfig?.contract_address ? (
              <>
                <span className="signal-note-label">Registry contract</span>
                <strong title={contractConfig.contract_address}>
                  {shortenHex(contractConfig.contract_address, 10, 8)}
                </strong>
                <div className="inline-links">
                  {addressUrl(
                    contractConfig.explorer_base_url,
                    contractConfig.contract_address,
                  ) ? (
                    <a
                      href={
                        addressUrl(
                          contractConfig.explorer_base_url,
                          contractConfig.contract_address,
                        ) ?? undefined
                      }
                      target="_blank"
                      rel="noreferrer"
                    >
                      View contract
                    </a>
                  ) : (
                    <span className="muted">
                      Local RPC mode: contract address available, no explorer link.
                    </span>
                  )}
                </div>
              </>
            ) : (
              <span className="muted">
                No deployed contract is configured yet. Publish and challenge actions
                stay unavailable until `/config` reports a live deployment.
              </span>
            )}
          </div>
        </div>
      </section>

      {/* ── Submit section: mode chips + form ────────────────── */}
      <section className="submit-section">
        <form className="submit-card" onSubmit={handleSubmit}>
          <div className="submit-card-heading">
            <div>
              <label htmlFor="contractAddress">Audit target</label>
              <p>
                Choose how the target code is available, then let the auditor
                prepare a claim that can later be published and challenged.
              </p>
            </div>
            {selectedFixture ? (
              <span className="fixture-pill">{selectedFixture.label}</span>
            ) : null}
          </div>
          <div className="mode-switch" role="tablist" aria-label="Audit input mode">
            <button
              className="mode-chip"
              data-selected={submissionMode === "demo_fixture"}
              type="button"
              onClick={() => setSubmissionMode("demo_fixture")}
            >
              Demo fixture
            </button>
            <button
              className="mode-chip"
              data-selected={submissionMode === "deployed_address"}
              type="button"
              onClick={() => setSubmissionMode("deployed_address")}
            >
              Deployed address
            </button>
            <button
              className="mode-chip"
              data-selected={submissionMode === "source_bundle"}
              type="button"
              onClick={() => setSubmissionMode("source_bundle")}
            >
              Source bundle
            </button>
          </div>
          {submissionMode === "source_bundle" ? (
            <div className="submission-fields">
              <input
                id="sourceBundleUri"
                name="sourceBundleUri"
                placeholder="ipfs://uploads/dual-risk-vault.zip"
                value={sourceBundleUri}
                onChange={(event) => setSourceBundleUri(event.target.value)}
              />
              <input
                id="entryContract"
                name="entryContract"
                placeholder="Entry contract (optional)"
                value={entryContract}
                onChange={(event) => setEntryContract(event.target.value)}
              />
              <input
                id="sourceBundleLabel"
                name="sourceBundleLabel"
                placeholder="Bundle label (optional)"
                value={sourceBundleLabel}
                onChange={(event) => setSourceBundleLabel(event.target.value)}
              />
            </div>
          ) : (
            <div className="submission-fields">
              <input
                id="contractAddress"
                name="contractAddress"
                placeholder="0x..."
                value={contractAddress}
                onChange={(event) => setContractAddress(event.target.value)}
                disabled={submissionMode === "demo_fixture"}
              />
              <input
                id="entryContract"
                name="entryContract"
                placeholder="Entry contract (optional)"
                value={entryContract}
                onChange={(event) => setEntryContract(event.target.value)}
              />
            </div>
          )}
          <div className="submit-card-footer">
            <p className="helper-copy">
              {submissionMode === "demo_fixture"
                ? selectedFixture
                  ? `${selectedFixture.contract_name} selected for a reproducible trust-and-challenge demo.`
                  : "Pick a demo fixture below to populate the live local address."
                : submissionMode === "source_bundle"
                  ? "Use a bundle URI when the agent needs source context before any claim can be published on-chain."
                  : "Paste a deployed contract address when you want the agent's claim to stay directly tied to on-chain code."}
            </p>
            <button type="submit" disabled={isPending}>
              {isPending && activeAction?.includes("Generating") ? "Working..." : "Generate claim"}
            </button>
          </div>
        </form>
        {/* Inline status chips */}
        <div className="status-chips">
          <div className="status-chip">
            <span>Mode</span>
            <strong>{submissionModeLabel(submissionMode)}</strong>
          </div>
          <div className="status-chip">
            <span>Coverage</span>
            <strong>{demoFixtures.length || 0} fixture paths</strong>
          </div>
          <div className="status-chip">
            <span>Auditor</span>
            <strong>
              {activeAudit ? activeAudit.agent.name : agentVersionLabel(contractConfig?.auditor)}
            </strong>
          </div>
        </div>
        {activeAction ? (
          <p className="notice-banner notice-banner-info">{activeAction}...</p>
        ) : null}
        {error ? <p className="error-banner">{error}</p> : null}
        {loadError ? <p className="error-banner">{loadError}</p> : null}
      </section>

      {/* ── Fixture selector strip ───────────────────────────── */}
      <section className="fixture-section">
        <div className="section-heading section-heading-wide">
          <div>
            <p>Demo fixtures</p>
            <strong className="section-subtitle">
              Pick a live contract to drive the trust, stake, and challenge flow
            </strong>
          </div>
          <span>{isLoaded ? `${demoFixtures.length} loaded` : "loading"}</span>
        </div>
        {!isLoaded ? (
          <article className="benchmark-empty">
            <p>Loading local fixtures and recent audit activity.</p>
            <span>The workbench is fetching API and chain metadata.</span>
          </article>
        ) : demoFixtures.length === 0 ? (
          <article className="benchmark-empty">
            <p>No local demo fixtures detected.</p>
            <span>
              Run <code>./scripts/deploy-demo-fixtures.sh</code> after local contract
              deployment to populate this panel with live Anvil addresses.
            </span>
          </article>
        ) : (
          <div className="benchmark-strip">
            {demoFixtures.map((fixture) => (
              <button
                key={fixture.address}
                className="benchmark-card"
                data-selected={fixture.id === selectedFixtureId}
                type="button"
                onClick={() => {
                  setSubmissionMode("demo_fixture");
                  setSelectedFixtureId(fixture.id);
                  setContractAddress(fixture.address);
                  setEntryContract(fixture.entry_contract);
                  setProofUri(fixture.challenge_proof_uri);
                }}
              >
                <div className="benchmark-card-topline">
                  <span>{fixture.label}</span>
                  <em>{fixture.entry_contract}</em>
                </div>
                <strong title={fixture.address}>
                  {shortenHex(fixture.address, 8, 6)}
                </strong>
                <p>{fixture.note}</p>
              </button>
            ))}
          </div>
        )}
      </section>

      {/* ── Main workspace: report + sidebar ─────────────────── */}
      <section className="workspace-grid">
        <article className="panel report-panel">
          <div className="section-heading">
            <p>Current audit</p>
            <span
              data-testid="current-audit-status"
              data-tone={statusTone(activeAudit?.status ?? "none")}
            >
              {activeAudit?.status ?? "none"}
            </span>
          </div>
          {activeAudit ? (
            <>
              {/* Summary + metadata — compact */}
              <div className="audit-summary-bar">
                <span>{activeAudit.agent.id}</span>
                <span>{submissionModeLabel(activeAudit.submission.input_kind)}</span>
                <span>{activeAudit.report.benchmark_id}</span>
                <span>{activeAudit.report.confidence} confidence</span>
                <span title={activeAudit.contract_address}>
                  {submissionTargetLabel(activeAudit)}
                </span>
              </div>
              <h2>{activeAudit.report.summary}</h2>
              <p className="muted">
                {activeAudit.agent.name} is the named actor responsible for this claim and
                any stake-backed publication that follows.
              </p>

              {/* Combined stats row: all key metrics in one strip */}
              <div className="stats-strip">
                <div>
                  <span>Auditor</span>
                  <strong>{activeAudit.agent.name}</strong>
                </div>
                <div>
                  <span>Status</span>
                  <strong>{lifecycleLabel(activeAudit)}</strong>
                </div>
                <div>
                  <span>Created</span>
                  <strong>{relativeTimeLabel(activeAudit.created_at)}</strong>
                </div>
                <div>
                  <span>Findings</span>
                  <strong>{activeAudit.report.finding_count}</strong>
                </div>
                <div>
                  <span>Max severity</span>
                  <strong>{activeAudit.report.max_severity}</strong>
                </div>
                <div>
                  <span>Report hash</span>
                  <strong title={activeAudit.report.report_hash}>
                    {shortenHex(activeAudit.report.report_hash, 10, 6)}
                  </strong>
                </div>
              </div>

              <p className="muted severity-mix">
                Severity mix:{" "}
                {Object.entries(activeAudit.report.severity_breakdown)
                  .filter(([, count]) => count > 0)
                  .map(([severity, count]) => `${titleCase(severity)} ${count}`)
                  .join(" · ") || "No findings"}
              </p>

              {/* ── Actions — promoted above findings ────────── */}
              <div className="action-row">
                <div className="action-card">
                  <span>Publish claim</span>
                  <strong>Stake {formatEth(publishStake)}</strong>
                  <p className="muted">
                    {activeAudit.submission.input_kind === "source_bundle"
                      ? "Deploy the reviewed source bundle first, then resubmit it as a deployed address before staking on-chain."
                      : `${activeAudit.agent.name} commits to this judgment on-chain so others can inspect and dispute it under fixed rules.`}
                  </p>
                  <button
                    type="button"
                    onClick={handlePublish}
                    disabled={
                      isPending ||
                      activeAudit.status !== "draft" ||
                      activeAudit.submission.input_kind === "source_bundle" ||
                      !contractConfig?.deployment_ready
                    }
                  >
                    {isPending && activeAction?.includes("publish")
                      ? "Publishing..."
                      : "Stake and publish"}
                  </button>
                </div>
                <div className="action-card action-card-wide">
                  <span>{challengePathLabel(activeAudit)}</span>
                  <strong>Bond {formatEth(challengeBond)}</strong>
                  <input
                    value={proofUri}
                    onChange={(event) => setProofUri(event.target.value)}
                    disabled={
                      isPending ||
                      activeAudit.status !== "published" ||
                      !contractConfig?.deployment_ready
                    }
                  />
                  <button
                    type="button"
                    onClick={handleChallenge}
                    disabled={
                      isPending ||
                      activeAudit.status !== "published" ||
                      !contractConfig?.deployment_ready
                    }
                  >
                    {isPending && activeAction?.includes("challenge")
                      ? "Challenging..."
                      : "Open challenge"}
                  </button>
                  <p className="muted">
                    Curated evidence artifact for the deterministic path:{" "}
                    <code>
                      {selectedFixture?.challenge_proof_uri ??
                        suggestedProofUriForBenchmark(activeAudit.report.benchmark_id)}
                    </code>
                  </p>
                  <p className="muted">{challengePathSummary(activeAudit)}</p>
                </div>
              </div>

              {/* ── On-chain attestation (if published) ──────── */}
              {activeAudit.onchain ? (
                <div className="onchain-card">
                  <div className="section-heading">
                    <p>On-chain commitment</p>
                    <span data-tone="confirmed">{activeAudit.onchain.network}</span>
                  </div>
                  <p className="muted">
                    {(activeAudit.onchain.agent_name ?? activeAudit.agent.name)} (
                    {activeAudit.onchain.agent_identity}) staked{" "}
                    {formatEth(activeAudit.onchain.stake_wei)} behind this judgment.
                  </p>
                  <div className="metadata-grid">
                    <div>
                      <span>Audit id</span>
                      <strong>{activeAudit.onchain.audit_id ?? "pending"}</strong>
                    </div>
                    <div>
                      <span>Contract</span>
                      <strong title={activeAudit.onchain.contract_address ?? ""}>
                        {activeAudit.onchain.contract_address
                          ? shortenHex(activeAudit.onchain.contract_address, 10, 8)
                          : "not reported"}
                      </strong>
                    </div>
                    <div>
                      <span>Publish tx</span>
                      <strong title={activeAudit.onchain.publish_tx_hash}>
                        {shortenHex(activeAudit.onchain.publish_tx_hash, 12, 8)}
                      </strong>
                    </div>
                  </div>
                  <div className="inline-links">
                    {activeAudit.onchain.publish_tx_url &&
                    isExplorerLink(activeAudit.onchain.publish_tx_url) ? (
                      <a
                        href={activeAudit.onchain.publish_tx_url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        View publish transaction
                      </a>
                    ) : (
                      <span className="muted">Publish tx confirmed on the local chain.</span>
                    )}
                    {addressUrl(
                      activeAudit.onchain.explorer_base_url,
                      activeAudit.onchain.contract_address ?? null,
                    ) ? (
                      <a
                        href={
                          addressUrl(
                            activeAudit.onchain.explorer_base_url,
                            activeAudit.onchain.contract_address ?? null,
                          ) ?? undefined
                        }
                        target="_blank"
                        rel="noreferrer"
                      >
                        View registry contract
                      </a>
                    ) : null}
                  </div>
                </div>
              ) : null}

              {/* ── Challenge details (if challenged) ────────── */}
              {activeAudit.challenge ? (
                <div className="challenge-card">
                  <div className="section-heading">
                    <p>Challenge and resolution</p>
                    <span
                      data-testid="challenge-status"
                      data-tone={statusTone(activeAudit.challenge.status)}
                    >
                      {activeAudit.challenge.status}
                    </span>
                  </div>
                  <p className="muted">{activeAudit.challenge.proof_uri}</p>
                  <div className="metadata-grid">
                    <div>
                      <span>Path</span>
                      <strong>{titleCase(activeAudit.challenge.resolution_path)}</strong>
                    </div>
                    <div>
                      <span>Challenger</span>
                      <strong title={activeAudit.challenge.challenger_address ?? ""}>
                        {activeAudit.challenge.challenger_address
                          ? shortenHex(activeAudit.challenge.challenger_address, 10, 8)
                          : activeAudit.challenge.challenger}
                      </strong>
                    </div>
                    <div>
                      <span>Bond</span>
                      <strong>
                        {activeAudit.challenge.challenge_bond_wei
                          ? formatEth(activeAudit.challenge.challenge_bond_wei)
                          : "n/a"}
                      </strong>
                    </div>
                    <div>
                      <span>Challenge tx</span>
                      <strong title={activeAudit.challenge.challenge_tx_hash}>
                        {shortenHex(activeAudit.challenge.challenge_tx_hash, 12, 8)}
                      </strong>
                    </div>
                  </div>
                  <div className="inline-links">
                    {activeAudit.challenge.challenge_tx_url &&
                    isExplorerLink(activeAudit.challenge.challenge_tx_url) ? (
                      <a
                        href={activeAudit.challenge.challenge_tx_url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        View challenge transaction
                      </a>
                    ) : (
                      <span className="muted">Challenge tx confirmed on the local chain.</span>
                    )}
                    {activeAudit.challenge.resolve_tx_url &&
                    isExplorerLink(activeAudit.challenge.resolve_tx_url) ? (
                      <a
                        href={activeAudit.challenge.resolve_tx_url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        View resolution transaction
                      </a>
                    ) : null}
                  </div>
                  {activeAudit.challenge.resolution ? (
                    <p className="muted">
                      Resolution {activeAudit.challenge.resolution} by{" "}
                      {activeAudit.challenge.resolved_by ?? "arbiter"} with payout{" "}
                      {activeAudit.challenge.payout_wei
                        ? formatEth(activeAudit.challenge.payout_wei)
                        : "pending"}.
                    </p>
                  ) : null}
                  <p className="muted">{challengePathSummary(activeAudit)}</p>
                  {activeAudit.challenge.verification_summary ? (
                    <p className="muted">
                      {activeAudit.challenge.verification_status ?? "verification"}:{" "}
                      {activeAudit.challenge.verification_summary}
                    </p>
                  ) : null}
                  {activeAudit.challenge.verification_detail ? (
                    <p className="muted">{activeAudit.challenge.verification_detail}</p>
                  ) : null}
                </div>
              ) : null}

              {/* ── Findings list ─────────────────────────────── */}
              <div className="finding-list">
                <div className="section-heading findings-heading">
                  <p>Findings</p>
                  <span>{activeAudit.report.findings.length}</span>
                </div>
                {activeAudit.report.findings.length === 0 ? (
                  <div className="finding-card">
                    <strong>No benchmark issue found</strong>
                    <p>
                      The auditor did not match a benchmark issue across the
                      supported checks, so no stronger claim is made here.
                    </p>
                  </div>
                ) : (
                  activeAudit.report.findings.map((finding) => (
                    <div key={finding.finding_id} className="finding-card">
                      <div className="card-header">
                        <p>{finding.title}</p>
                        <span>{finding.severity}</span>
                      </div>
                      <p className="muted">
                        {titleCase(finding.category)} · {titleCase(finding.confidence)}
                        {" "}confidence
                        {finding.affected_function ? ` · ${finding.affected_function}` : ""}
                      </p>
                      <p>{finding.description}</p>
                      <p className="muted">{finding.impact}</p>
                      <p className="muted">{finding.recommendation}</p>
                      {finding.source_path ? (
                        <p className="muted">
                          Source: {finding.source_path}
                          {finding.start_line ? `:${finding.start_line}` : ""}
                          {finding.end_line && finding.end_line !== finding.start_line
                            ? `-${finding.end_line}`
                            : ""}
                        </p>
                      ) : null}
                      {finding.evidence_uri ? (
                        <p className="muted">Evidence: {finding.evidence_uri}</p>
                      ) : null}
                    </div>
                  ))
                )}
              </div>
            </>
          ) : (
            <div className="empty-panel">
              <strong>No active audit selected</strong>
              <p className="muted">
                Generate a claim to populate the workbench, or pick one from recent
                activity once the API data loads.
              </p>
            </div>
          )}
        </article>

        <aside className="panel recent-panel">
          <div className="section-heading">
            <p>Recent claims</p>
            <span>{recentAudits.length}</span>
          </div>
          <div className="recent-list">
            {!isLoaded ? (
              <p className="muted">Loading recent audits.</p>
            ) : recentAudits.length === 0 ? (
              <p className="muted">No audits yet.</p>
            ) : (
              recentAudits.map((audit) => (
                <button
                  key={audit.id}
                  type="button"
                  className="recent-item"
                  data-selected={audit.id === activeAudit?.id}
                  onClick={() => syncAudit(audit)}
                >
                  <div className="card-header">
                    <p>{audit.report.benchmark_id}</p>
                    <span data-tone={statusTone(audit.status)}>{audit.status}</span>
                  </div>
                  <small>{audit.agent.name}</small>
                  <strong title={audit.contract_address}>{submissionTargetLabel(audit)}</strong>
                  <p>{audit.report.summary}</p>
                  <small>{lifecycleLabel(audit)}</small>
                </button>
              ))
            )}
          </div>
        </aside>
      </section>
    </main>
  );
}
