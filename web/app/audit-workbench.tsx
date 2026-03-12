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

const API_BASE_URL =
  process.env.NEXT_PUBLIC_PROOF_OF_AUDIT_API_URL ?? "http://127.0.0.1:8080";

const benchmarkCards = [
  {
    label: "Vulnerable Bank",
    address: "0x1000000000000000000000000000000000000001",
    note: "High-confidence reentrancy finding",
  },
  {
    label: "Admin Setter",
    address: "0x1000000000000000000000000000000000000002",
    note: "High-confidence access control finding",
  },
  {
    label: "Clean Vault",
    address: "0x1000000000000000000000000000000000000003",
    note: "Clean benchmark with medium confidence",
  },
];

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

export function AuditWorkbench() {
  const [contractAddress, setContractAddress] = useState(
    "0x1000000000000000000000000000000000000001",
  );
  const [recentAudits, setRecentAudits] = useState<AuditRecord[]>([]);
  const [activeAudit, setActiveAudit] = useState<AuditRecord | null>(null);
  const [proofUri, setProofUri] = useState("ipfs://demo-poc");
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  useEffect(() => {
    startTransition(() => {
      void loadRecentAudits();
    });
  }, []);

  async function loadRecentAudits() {
    try {
      const payload = await apiFetch<{ items: AuditRecord[] }>("/audits");
      setRecentAudits(payload.items);
      if (!activeAudit && payload.items.length > 0) {
        setActiveAudit(payload.items[0]);
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
          <p className="eyebrow">Base Sepolia Demo</p>
          <h1>Agents that stake on their audit calls.</h1>
          <p className="lede">
            Submit a contract, generate a deterministic report, publish a staked
            attestation, and challenge it with reproducible evidence.
          </p>
          <form className="submit-card" onSubmit={handleSubmit}>
            <label htmlFor="contractAddress">Contract address</label>
            <input
              id="contractAddress"
              name="contractAddress"
              value={contractAddress}
              onChange={(event) => setContractAddress(event.target.value)}
            />
            <button type="submit" disabled={isPending}>
              {isPending ? "Working..." : "Run audit"}
            </button>
          </form>
          {error ? <p className="error-banner">{error}</p> : null}
        </div>
        <div className="signal-panel">
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
            <strong>Deterministic verifier, immediate resolution</strong>
          </div>
        </div>
      </section>

      <section className="benchmark-strip">
        {benchmarkCards.map((benchmark) => (
          <button
            key={benchmark.address}
            className="benchmark-card"
            type="button"
            onClick={() => setContractAddress(benchmark.address)}
          >
            <span>{benchmark.label}</span>
            <strong>{benchmark.address}</strong>
            <p>{benchmark.note}</p>
          </button>
        ))}
      </section>

      <section className="workspace-grid">
        <article className="panel report-panel">
          <div className="section-heading">
            <p>Current audit</p>
            <span>{activeAudit?.status ?? "none"}</span>
          </div>
          {activeAudit ? (
            <>
              <h2>{activeAudit.report.summary}</h2>
              <p className="muted">
                {activeAudit.contract_address} · {activeAudit.report.benchmark_id} ·{" "}
                {activeAudit.report.confidence} confidence
              </p>
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
                  <strong>{activeAudit.report.report_hash.slice(0, 10)}...</strong>
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
                <button
                  type="button"
                  onClick={handlePublish}
                  disabled={isPending || activeAudit.status !== "draft"}
                >
                  Publish stake
                </button>
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
                  <p className="mono">
                    publish tx: {activeAudit.onchain.publish_tx_hash}
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
                  <p className="mono">
                    challenge tx: {activeAudit.challenge.challenge_tx_hash}
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
                  onClick={() => setActiveAudit(audit)}
                >
                  <div className="card-header">
                    <p>{audit.report.benchmark_id}</p>
                    <span>{audit.status}</span>
                  </div>
                  <strong>{audit.contract_address}</strong>
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
