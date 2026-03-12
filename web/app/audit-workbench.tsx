"use client";

import { FormEvent, useEffect, useState, useTransition } from "react";

type Finding = {
  title: string;
  severity: string;
  description: string;
  recommendation: string;
  detector: string;
};

type AuditRecord = {
  id: string;
  contract_address: string;
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
  };
  onchain: null | {
    audit_id?: number;
    network: string;
    agent_identity: string;
    stake_wei: number;
    report_hash: string;
    metadata_hash: string;
    max_severity: number;
    finding_count: number;
    publish_tx_hash: string;
  };
  challenge: null | {
    challenger: string;
    proof_uri: string;
    submitted_at: string;
    verifier: string;
    status: string;
    challenge_tx_hash: string;
  };
};

type DemoFixture = {
  id: string;
  label: string;
  contract_name: string;
  entry_contract: string;
  benchmark_id: string;
  address: string;
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

function shortenHex(value: string, start = 6, end = 4): string {
  if (value.length <= start + end + 3) {
    return value;
  }
  return `${value.slice(0, start)}...${value.slice(-end)}`;
}

export function AuditWorkbench() {
  const [contractAddress, setContractAddress] = useState("");
  const [demoFixtures, setDemoFixtures] = useState<DemoFixture[]>([]);
  const [recentAudits, setRecentAudits] = useState<AuditRecord[]>([]);
  const [activeAudit, setActiveAudit] = useState<AuditRecord | null>(null);
  const [proofUri, setProofUri] = useState("ipfs://demo-poc");
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();
  const selectedFixture =
    demoFixtures.find((fixture) => fixture.address === contractAddress) ?? null;

  useEffect(() => {
    startTransition(() => {
      void loadRecentAudits();
    });
  }, []);

  async function loadRecentAudits() {
    try {
      const [auditPayload, fixturePayload] = await Promise.all([
        apiFetch<{ items: AuditRecord[] }>("/audits"),
        apiFetch<{ items: DemoFixture[] }>("/fixtures"),
      ]);
      setRecentAudits(auditPayload.items);
      setDemoFixtures(fixturePayload.items);
      if (!activeAudit && auditPayload.items.length > 0) {
        setActiveAudit(auditPayload.items[0]);
      }
      if (!contractAddress && fixturePayload.items.length > 0) {
        setContractAddress(fixturePayload.items[0].address);
      }
    } catch (loadError) {
      setError(
        loadError instanceof Error ? loadError.message : "Failed to load audits",
      );
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    startTransition(() => {
      void (async () => {
        try {
          const created = await apiFetch<AuditRecord>("/audits", {
            method: "POST",
            body: JSON.stringify({
              contract_address: contractAddress,
              submitted_by: "web-demo",
            }),
          });
          setActiveAudit(created);
          setRecentAudits((current) => [created, ...current]);
        } catch (submitError) {
          setError(
            submitError instanceof Error
              ? submitError.message
              : "Failed to create audit",
          );
        }
      })();
    });
  }

  async function handlePublish() {
    if (!activeAudit) {
      return;
    }
    setError(null);

    startTransition(() => {
      void (async () => {
        try {
          const published = await apiFetch<AuditRecord>(
            `/audits/${activeAudit.id}/publish`,
            {
              method: "POST",
              body: JSON.stringify({
                stake_wei: 10_000_000_000_000_000,
                agent_identity: "auditor-agent-v1",
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
        }
      })();
    });
  }

  async function handleChallenge() {
    if (!activeAudit) {
      return;
    }
    setError(null);

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
        }
      })();
    });
  }

  function syncAudit(nextAudit: AuditRecord) {
    setActiveAudit(nextAudit);
    setRecentAudits((current) =>
      [nextAudit, ...current.filter((audit) => audit.id !== nextAudit.id)].sort(
        (left, right) => right.created_at.localeCompare(left.created_at),
      ),
    );
  }

  return (
    <main className="page-shell">
      <section className="hero">
        <div className="hero-copy">
          <p className="eyebrow">Proof-of-Audit Workbench</p>
          <h1>Agents that stake on their audit calls.</h1>
          <p className="lede">
            Submit a contract, generate a deterministic report, publish a staked
            attestation, and challenge it with reproducible evidence.
          </p>
          <div className="hero-inline-metrics">
            <div>
              <span>Mode</span>
              <strong>Local fixture demo</strong>
            </div>
            <div>
              <span>Coverage</span>
              <strong>4 fixture paths</strong>
            </div>
            <div>
              <span>Resolution</span>
              <strong>On-chain challenge opening</strong>
            </div>
          </div>
          <form className="submit-card" onSubmit={handleSubmit}>
            <div className="submit-card-heading">
              <div>
                <label htmlFor="contractAddress">Audit target</label>
                <p>
                  Paste an address or pick one of the local fixtures below to
                  populate the form.
                </p>
              </div>
              {selectedFixture ? (
                <span className="fixture-pill">{selectedFixture.label}</span>
              ) : null}
            </div>
            <input
              id="contractAddress"
              name="contractAddress"
              placeholder="0x..."
              value={contractAddress}
              onChange={(event) => setContractAddress(event.target.value)}
            />
            <div className="submit-card-footer">
              <p className="helper-copy">
                {selectedFixture
                  ? `${selectedFixture.contract_name} selected from local Anvil fixtures.`
                  : "No fixture selected. You can still submit any deployed contract address."}
              </p>
              <button type="submit" disabled={isPending}>
                {isPending ? "Working..." : "Run audit"}
              </button>
            </div>
          </form>
          {error ? <p className="error-banner">{error}</p> : null}
        </div>
        <div className="signal-panel">
          <div className="panel-kicker">
            <span>Live demo configuration</span>
            <strong>Operator view</strong>
          </div>
          <div className="signal-row">
            <span>Supported checks</span>
            <strong>Reentrancy, access control, unchecked calls</strong>
          </div>
          <div className="signal-row">
            <span>Economic commitment</span>
            <strong>0.01 ETH stake per published audit</strong>
          </div>
          <div className="signal-row">
            <span>Challenge path</span>
            <strong>Real challenge transactions, resolution follows</strong>
          </div>
          <div className="signal-note">
            Local fixtures are deployed to Anvil and surfaced through the API,
            so the UI reflects live addresses instead of baked-in demo values.
          </div>
        </div>
      </section>

      <section className="fixture-section">
        <div className="section-heading section-heading-wide">
          <div>
            <p>Demo fixtures</p>
            <strong className="section-subtitle">
              Pick a live local contract to drive the audit flow
            </strong>
          </div>
          <span>{demoFixtures.length} loaded</span>
        </div>
        {demoFixtures.length === 0 ? (
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
                data-selected={fixture.address === contractAddress}
                type="button"
                onClick={() => setContractAddress(fixture.address)}
              >
                <div className="benchmark-card-topline">
                  <span>{fixture.label}</span>
                  <em>{fixture.entry_contract}</em>
                </div>
                <strong title={fixture.address}>{shortenHex(fixture.address, 8, 6)}</strong>
                <p>{fixture.note}</p>
              </button>
            ))}
          </div>
        )}
      </section>

      <section className="workspace-grid">
        <article className="panel report-panel">
          <div className="section-heading">
            <p>Current audit</p>
            <span>{activeAudit?.status ?? "none"}</span>
          </div>
          {activeAudit ? (
            <>
              <div className="audit-summary-bar">
                <span>{activeAudit.report.benchmark_id}</span>
                <span>{activeAudit.report.confidence} confidence</span>
                <span title={activeAudit.contract_address}>
                  {shortenHex(activeAudit.contract_address, 8, 6)}
                </span>
              </div>
              <h2>{activeAudit.report.summary}</h2>
              <div className="stat-row">
                <div>
                  <span>Findings</span>
                  <strong>{activeAudit.report.findings.length}</strong>
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

              <div className="finding-list">
                {activeAudit.report.findings.length === 0 ? (
                  <div className="finding-card">
                    <strong>No benchmark issue found</strong>
                    <p>
                      The worker did not match a benchmark vulnerability across
                      the supported checks.
                    </p>
                  </div>
                ) : (
                  activeAudit.report.findings.map((finding) => (
                    <div key={finding.title} className="finding-card">
                      <div className="card-header">
                        <p>{finding.title}</p>
                        <span>{finding.severity}</span>
                      </div>
                      <p>{finding.description}</p>
                      <p className="muted">{finding.recommendation}</p>
                    </div>
                  ))
                )}
              </div>

              <div className="action-row">
                <div className="action-card">
                  <span>Publish</span>
                  <strong>Stake {formatEth(10_000_000_000_000_000)}</strong>
                  <button
                    type="button"
                    onClick={handlePublish}
                    disabled={isPending || activeAudit.status !== "draft"}
                  >
                    Publish stake
                  </button>
                </div>
                <div className="action-card action-card-wide">
                  <span>Challenge proof</span>
                  <input
                    value={proofUri}
                    onChange={(event) => setProofUri(event.target.value)}
                    disabled={isPending || activeAudit.status !== "published"}
                  />
                  <button
                    type="button"
                    onClick={handleChallenge}
                    disabled={isPending || activeAudit.status !== "published"}
                  >
                    Challenge with PoC
                  </button>
                </div>
              </div>

              {activeAudit.onchain ? (
                <div className="onchain-card">
                  <div className="section-heading">
                    <p>On-chain attestation</p>
                    <span>{activeAudit.onchain.network}</span>
                  </div>
                  <p className="muted">
                    {activeAudit.onchain.agent_identity} staked{" "}
                    {formatEth(activeAudit.onchain.stake_wei)} behind this report.
                  </p>
                  <p className="mono" title={activeAudit.onchain.publish_tx_hash}>
                    publish tx: {shortenHex(activeAudit.onchain.publish_tx_hash, 12, 8)}
                  </p>
                </div>
              ) : null}

              {activeAudit.challenge ? (
                <div className="challenge-card">
                  <div className="section-heading">
                    <p>Challenge status</p>
                    <span>{activeAudit.challenge.status}</span>
                  </div>
                  <p className="muted">{activeAudit.challenge.proof_uri}</p>
                  <p className="mono" title={activeAudit.challenge.challenge_tx_hash}>
                    challenge tx:{" "}
                    {shortenHex(activeAudit.challenge.challenge_tx_hash, 12, 8)}
                  </p>
                </div>
              ) : null}
            </>
          ) : (
            <p className="muted">
              Create an audit to populate the workbench, or pick one from recent
              activity.
            </p>
          )}
        </article>

        <aside className="panel recent-panel">
          <div className="section-heading">
            <p>Recent audits</p>
            <span>{recentAudits.length}</span>
          </div>
          <div className="recent-list">
            {recentAudits.length === 0 ? (
              <p className="muted">No audits yet.</p>
            ) : (
              recentAudits.map((audit) => (
                <button
                  key={audit.id}
                  type="button"
                  className="recent-item"
                  data-selected={audit.id === activeAudit?.id}
                  onClick={() => setActiveAudit(audit)}
                >
                  <div className="card-header">
                    <p>{audit.report.benchmark_id}</p>
                    <span>{audit.status}</span>
                  </div>
                  <strong title={audit.contract_address}>
                    {shortenHex(audit.contract_address, 8, 6)}
                  </strong>
                  <p>{audit.report.summary}</p>
                </button>
              ))
            )}
          </div>
        </aside>
      </section>
    </main>
  );
}
