"use client";

import { FormEvent, useEffect, useState, useTransition } from "react";
import { apiFetch } from "./lib/api";
import { suggestedProofUriForBenchmark } from "./lib/format";
import type {
  AuditRecord,
  AuditorServiceRecord,
  DemoFixture,
  InputKind,
  PublicContractConfig,
  TargetComparisonResponse,
} from "./lib/types";
import { Navbar } from "./components/navbar";
import { Sidebar } from "./components/sidebar";
import { PhaseStepper } from "./components/phase-stepper";
import { SubmitPanel } from "./components/submit-panel";
import { FixtureStrip } from "./components/fixture-strip";
import { AuditCard } from "./components/audit-card";
import { ActionsPanel } from "./components/actions-panel";
import { OnchainCard } from "./components/onchain-card";
import { ValidationCard } from "./components/validation-card";
import { ChallengeCard } from "./components/challenge-card";
import { AgentSidebar } from "./components/agent-sidebar";
import { RecentClaims } from "./components/recent-claims";
import { TargetComparison } from "./components/target-comparison";
import { PublishedView } from "./components/views/published-view";
import { ReputationView } from "./components/views/reputation-view";
import { DisputedView } from "./components/views/disputed-view";
import { ArchiveView } from "./components/views/archive-view";

function preferredDemoFixture(fixtures: DemoFixture[]): DemoFixture | null {
  if (fixtures.length === 0) return null;
  return fixtures.find((f) => f.id === "clean-vault") ?? fixtures[0];
}

const VIEW_LABELS: Record<string, { eyebrow: string; title: string; desc: string }> = {
  workbench:  { eyebrow: "Workspace",       title: "Audit Workbench",    desc: "Upload smart contract artifacts or point to a mainnet address to initialize the forensic verification engine." },
  published:  { eyebrow: "Published Claims", title: "Published",          desc: "Claims that have been staked and published on-chain. These can be challenged within the challenge window." },
  disputed:   { eyebrow: "Disputed Claims",  title: "Disputed",           desc: "Claims that have been challenged and are awaiting resolution through deterministic or manual paths." },
  reputation: { eyebrow: "Trust Network",    title: "Auditor Reputation", desc: "View trust scores, resolved challenges, and reputation metrics for auditor agents." },
  archive:    { eyebrow: "Archive",          title: "Archive",            desc: "Completed and resolved audit claims that have exited the challenge window." },
};

const VIEW_STATUS_MAP: Record<string, string[]> = {
  workbench:  [],
  published:  ["published"],
  disputed:   ["challenged"],
  reputation: ["resolved"],
  archive:    ["resolved"],
};

export function AuditWorkbench() {
  /* ── sidebar state ────────────────────────────────────── */
  const [activeView, setActiveView] = useState("workbench");

  /* ── view filtering ──────────────────────────────────── */
  function handleViewChange(view: string) {
    setActiveView(view);
    const statuses = VIEW_STATUS_MAP[view] ?? [];
    if (statuses.length > 0) {
      const match = recentAudits.find((a) => statuses.includes(a.status));
      if (match) setActiveAudit(match);
    }
    // Scroll to top of content
    document.querySelector(".page-shell")?.scrollTo({ top: 0, behavior: "smooth" });
  }

  function handleNewClaim() {
    setActiveView("workbench");
    setTimeout(() => {
      document.getElementById("submit-section")?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 50);
  }

  function handleScrollTo(sectionId: string) {
    document.getElementById(sectionId)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  /* ── form state ─────────────────────────────────────── */
  const [submissionMode, setSubmissionMode] = useState<InputKind>("demo_fixture");
  const [contractAddress, setContractAddress] = useState("");
  const [selectedFixtureId, setSelectedFixtureId] = useState("");
  const [entryContract, setEntryContract] = useState("");
  const [sourceBundleUri, setSourceBundleUri] = useState("");
  const [sourceBundleLabel, setSourceBundleLabel] = useState("");
  const [proofUri, setProofUri] = useState("ipfs://demo-poc");

  /* ── data ───────────────────────────────────────────── */
  const [demoFixtures, setDemoFixtures] = useState<DemoFixture[]>([]);
  const [recentAudits, setRecentAudits] = useState<AuditRecord[]>([]);
  const [targetComparison, setTargetComparison] = useState<TargetComparisonResponse | null>(null);
  const [activeAudit, setActiveAudit] = useState<AuditRecord | null>(null);
  const [contractConfig, setContractConfig] = useState<PublicContractConfig | null>(null);
  const [auditorService, setAuditorService] = useState<AuditorServiceRecord | null>(null);

  /* ── ui state ───────────────────────────────────────── */
  const [error, setError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isLoaded, setIsLoaded] = useState(false);
  const [isComparisonLoaded, setIsComparisonLoaded] = useState(false);
  const [activeAction, setActiveAction] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  const selectedFixture =
    demoFixtures.find((f) => f.id === selectedFixtureId) ??
    demoFixtures.find((f) => f.address === contractAddress) ??
    undefined;
  const publishStake = contractConfig?.required_stake_wei ?? 10_000_000_000_000_000;
  const challengeBond = contractConfig?.required_challenge_bond_wei ?? 5_000_000_000_000_000;

  /* ── view-filtered audits ────────────────────────────── */
  const filteredAudits = (() => {
    const statuses = VIEW_STATUS_MAP[activeView] ?? [];
    if (statuses.length === 0) return recentAudits;
    return recentAudits.filter((a) => statuses.includes(a.status));
  })();

  /* ── data loading ───────────────────────────────────── */
  useEffect(() => {
    startTransition(() => void loadWorkbench());
  }, []);

  useEffect(() => {
    if (!activeAudit?.contract_address) {
      setTargetComparison(null);
      setIsComparisonLoaded(false);
      return;
    }
    startTransition(() => void loadTargetComparison(activeAudit.contract_address));
  }, [activeAudit?.id, activeAudit?.contract_address]);

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
        setActiveAudit((c) => c ?? auditPayload.items[0]);
      }
      if (fixturePayload.items.length > 0 && !selectedFixtureId) {
        const first = preferredDemoFixture(fixturePayload.items);
        if (first) {
          setSubmissionMode("demo_fixture");
          setSelectedFixtureId(first.id);
          setContractAddress(first.address);
          setEntryContract(first.entry_contract);
          setProofUri(first.challenge_proof_uri);
        }
      }
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "Failed to load workbench");
    } finally {
      setIsLoaded(true);
    }
  }

  async function loadTargetComparison(addr: string) {
    setIsComparisonLoaded(false);
    try {
      setTargetComparison(await apiFetch<TargetComparisonResponse>(`/targets/${addr}/comparison`));
    } catch {
      setTargetComparison(null);
    } finally {
      setIsComparisonLoaded(true);
    }
  }

  /* ── actions ────────────────────────────────────────── */
  function syncAudit(next: AuditRecord) {
    setActiveAudit(next);
    setSubmissionMode(next.submission.input_kind);
    setContractAddress(next.submission.contract_address ?? next.contract_address);
    setSelectedFixtureId(next.submission.fixture_id ?? "");
    setEntryContract(next.submission.entry_contract ?? "");
    setSourceBundleUri(next.submission.source_bundle_uri ?? "");
    setSourceBundleLabel(next.submission.source_bundle_label ?? "");
    setProofUri(suggestedProofUriForBenchmark(next.report.benchmark_id));
    setRecentAudits((cur) =>
      [next, ...cur.filter((a) => a.id !== next.id)].sort(
        (a, b) => b.created_at.localeCompare(a.created_at),
      ),
    );
  }

  async function handleSubmit(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    setError(null);
    setActiveAction("Generating deterministic audit report");
    startTransition(() =>
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
          syncAudit(await apiFetch<AuditRecord>("/audits", { method: "POST", body: JSON.stringify(payload) }));
        } catch (e) {
          setError(e instanceof Error ? e.message : "Failed to create audit");
        } finally {
          setActiveAction(null);
        }
      })(),
    );
  }

  async function handlePublish() {
    if (!activeAudit) return;
    setError(null);
    setActiveAction("Submitting publish transaction");
    startTransition(() =>
      void (async () => {
        try {
          syncAudit(await apiFetch<AuditRecord>(`/audits/${activeAudit.id}/publish`, {
            method: "POST",
            body: JSON.stringify({ stake_wei: publishStake }),
          }));
        } catch (e) {
          setError(e instanceof Error ? e.message : "Failed to publish");
        } finally {
          setActiveAction(null);
        }
      })(),
    );
  }

  async function handleChallenge() {
    if (!activeAudit) return;
    setError(null);
    setActiveAction("Opening challenge transaction");
    startTransition(() =>
      void (async () => {
        try {
          syncAudit(await apiFetch<AuditRecord>(`/audits/${activeAudit.id}/challenge`, {
            method: "POST",
            body: JSON.stringify({ proof_uri: proofUri, challenger: "whitehat-demo" }),
          }));
        } catch (e) {
          setError(e instanceof Error ? e.message : "Failed to challenge");
        } finally {
          setActiveAction(null);
        }
      })(),
    );
  }

  /* ── render ─────────────────────────────────────────── */
  return (
    <div className="app-shell">
      <Sidebar activeView={activeView} onViewChange={handleViewChange} onNewClaim={handleNewClaim} />
      <Navbar config={contractConfig} onScrollTo={handleScrollTo} />

      <main className="page-shell">
        {/* Page header */}
        <div className="page-header">
          <div className="page-header-left">
            <div className="page-eyebrow">
              <span>{VIEW_LABELS[activeView]?.eyebrow ?? "Workspace"}</span>
              <div className="health-badge">
                <span className="health-dot" />
                <span>System Healthy</span>
              </div>
            </div>
            <h1>{VIEW_LABELS[activeView]?.title ?? "Audit Workbench"}</h1>
            <p>{VIEW_LABELS[activeView]?.desc ?? "Upload smart contract artifacts or point to a mainnet address to initialize the forensic verification engine."}</p>
          </div>
          <div className="page-meta-badge">
            ⏱ AUTO-SAVE: 2 MIN AGO
          </div>
        </div>

        {/* Phase stepper — workbench only */}
        {activeView === "workbench" ? <PhaseStepper audit={activeAudit} /> : null}

        {/* ── View-specific content ── */}
        {activeView === "workbench" ? (
          <>
            {/* Main workspace: submission + audit report */}
            <section id="workspace-section" className="workspace-grid">
              {/* Left column: submit + meta */}
              <div id="submit-section" style={{ display: "grid", gap: 20, alignContent: "start" }}>
                <SubmitPanel
                  submissionMode={submissionMode}
                  contractAddress={contractAddress}
                  selectedFixtureId={selectedFixtureId}
                  entryContract={entryContract}
                  sourceBundleUri={sourceBundleUri}
                  sourceBundleLabel={sourceBundleLabel}
                  selectedFixture={selectedFixture}
                  isPending={isPending}
                  activeAction={activeAction}
                  config={contractConfig}
                  onModeChange={setSubmissionMode}
                  onContractAddressChange={setContractAddress}
                  onEntryContractChange={setEntryContract}
                  onSourceBundleUriChange={setSourceBundleUri}
                  onSourceBundleLabelChange={setSourceBundleLabel}
                  onSubmit={() => handleSubmit()}
                />
                {activeAction ? (
                  <p className="notice-banner notice-banner-info">{activeAction}…</p>
                ) : null}
                {error ? <p className="error-banner">{error}</p> : null}
                {loadError ? <p className="error-banner">{loadError}</p> : null}

                {/* Meta bento */}
                <div className="meta-bento">
                  <div className="meta-bento-item">
                    <div className="meta-label">Audit Type</div>
                    <div className="meta-value">Automated Pro</div>
                  </div>
                  <div className="meta-bento-item">
                    <div className="meta-label">Version</div>
                    <div className="meta-value">v2.4.1-alpha</div>
                  </div>
                </div>

                {/* Agent sidebar cards */}
                <div id="agent-info">
                  <AgentSidebar
                    config={contractConfig}
                    auditorService={auditorService}
                    publishStake={publishStake}
                    challengeBond={challengeBond}
                  />
                </div>
              </div>

              {/* Right column: audit report */}
              <div id="audit-report" style={{ display: "grid", gap: 20, alignContent: "start" }}>
                {activeAudit ? (
                  <>
                    <AuditCard audit={activeAudit} />
                    <ActionsPanel
                      audit={activeAudit}
                      config={contractConfig}
                      proofUri={proofUri}
                      isPending={isPending}
                      activeAction={activeAction}
                      publishStake={publishStake}
                      challengeBond={challengeBond}
                      onProofUriChange={setProofUri}
                      onPublish={handlePublish}
                      onChallenge={handleChallenge}
                    />
                    <OnchainCard audit={activeAudit} />
                    <ValidationCard audit={activeAudit} />
                    <ChallengeCard audit={activeAudit} />
                    <TargetComparison
                      audit={activeAudit}
                      comparison={targetComparison}
                      isLoaded={isComparisonLoaded}
                      onSelect={syncAudit}
                    />
                    <RecentClaims
                      audits={filteredAudits}
                      activeId={activeAudit?.id ?? null}
                      isLoaded={isLoaded}
                      onSelect={syncAudit}
                    />
                  </>
                ) : (
                  <div className="card">
                    <div className="empty-panel">
                      <strong>No active audit selected</strong>
                      <p className="muted">
                        Generate a claim to populate the workbench, or pick one from recent activity.
                      </p>
                    </div>
                  </div>
                )}
              </div>
            </section>

            {/* Fixtures — at the bottom */}
            <div id="fixture-strip">
              <FixtureStrip
                fixtures={demoFixtures}
                selectedId={selectedFixtureId}
                isLoaded={isLoaded}
                onSelect={(f) => {
                  setSubmissionMode("demo_fixture");
                  setSelectedFixtureId(f.id);
                  setContractAddress(f.address);
                  setEntryContract(f.entry_contract);
                  setProofUri(f.challenge_proof_uri);
                }}
              />
            </div>
          </>
        ) : activeView === "published" ? (
          activeAudit ? (
            <PublishedView audit={activeAudit} allAudits={recentAudits} onSelect={syncAudit} />
          ) : (
            <div className="card"><div className="empty-panel"><strong>No published claims found</strong><p className="muted">Publish an audit claim from the workbench to see it here.</p></div></div>
          )
        ) : activeView === "disputed" ? (
          activeAudit ? (
            <DisputedView audit={activeAudit} allAudits={recentAudits} onSelect={syncAudit} />
          ) : (
            <div className="card"><div className="empty-panel"><strong>No disputed claims</strong><p className="muted">No claims are currently under dispute.</p></div></div>
          )
        ) : activeView === "reputation" ? (
          <ReputationView config={contractConfig} audits={recentAudits} auditorService={auditorService} />
        ) : activeView === "archive" ? (
          <ArchiveView audits={recentAudits} onSelect={syncAudit} />
        ) : null}

        {/* Footer data */}
        <div className="footer-data">
          <div className="footer-item">💻 Logs: Syncing...</div>
          <div className="footer-item">🔗 Nodes: 12 Active</div>
          <div className="footer-item">⛓ Block: 18,241,002</div>
        </div>
      </main>
    </div>
  );
}
