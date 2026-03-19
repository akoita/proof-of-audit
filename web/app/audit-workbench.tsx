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
import { PhaseStepper } from "./components/phase-stepper";
import { SubmitPanel } from "./components/submit-panel";
import { FixtureStrip } from "./components/fixture-strip";
import { AuditCard } from "./components/audit-card";
import { ActionsPanel } from "./components/actions-panel";
import { OnchainCard } from "./components/onchain-card";
import { ValidationCard } from "./components/validation-card";
import { ChallengeCard } from "./components/challenge-card";
import { FindingsList } from "./components/findings-list";
import { AgentSidebar } from "./components/agent-sidebar";
import { RecentClaims } from "./components/recent-claims";
import { TargetComparison } from "./components/target-comparison";

function preferredDemoFixture(fixtures: DemoFixture[]): DemoFixture | null {
  if (fixtures.length === 0) return null;
  return fixtures.find((f) => f.id === "clean-vault") ?? fixtures[0];
}

export function AuditWorkbench() {
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
    null;
  const publishStake = contractConfig?.required_stake_wei ?? 10_000_000_000_000_000;
  const challengeBond = contractConfig?.required_challenge_bond_wei ?? 5_000_000_000_000_000;

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

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
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
      <Navbar config={contractConfig} />

      <main className="page-shell">
        {/* Phase stepper */}
        <PhaseStepper audit={activeAudit} />

        {/* Hero */}
        <section className="hero">
          <div className="hero-copy">
            <p className="eyebrow">Proof-of-Audit Workbench</p>
            <h1>Trust and challengeability for agent-made code judgments.</h1>
            <p className="lede">
              A named auditor agent makes a claim about a contract, stakes behind
              it, and can be challenged through a neutral on-chain process.
            </p>
            <div className="deployment-banner">
              <span className="deployment-badge">✓ Verified on Base Sepolia</span>
              <a
                href="https://sepolia.basescan.org/address/0xf2dA3947d028b85e597Fe1Df4633a87eF4A85F24"
                target="_blank"
                rel="noreferrer"
                className="deployment-link"
              >
                View ProofOfAudit contract on Basescan ↗
              </a>
            </div>
          </div>
        </section>

        {/* Submit */}
        <section className="submit-section">
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
            onSubmit={handleSubmit}
          />
          {activeAction ? (
            <p className="notice-banner notice-banner-info">{activeAction}…</p>
          ) : null}
          {error ? <p className="error-banner">{error}</p> : null}
          {loadError ? <p className="error-banner">{loadError}</p> : null}
        </section>

        {/* Fixtures */}
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

        {/* Main workspace */}
        <section className="workspace-grid">
          <article className="panel report-panel">
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
                <FindingsList findings={activeAudit.report.findings} />
              </>
            ) : (
              <div className="empty-panel">
                <strong>No active audit selected</strong>
                <p className="muted">
                  Generate a claim to populate the workbench, or pick one from recent activity.
                </p>
              </div>
            )}
          </article>

          <aside className="panel recent-panel">
            <AgentSidebar
              config={contractConfig}
              auditorService={auditorService}
              publishStake={publishStake}
              challengeBond={challengeBond}
            />
            <TargetComparison
              audit={activeAudit}
              comparison={targetComparison}
              isLoaded={isComparisonLoaded}
              onSelect={syncAudit}
            />
            <RecentClaims
              audits={recentAudits}
              activeId={activeAudit?.id ?? null}
              isLoaded={isLoaded}
              onSelect={syncAudit}
            />
          </aside>
        </section>
      </main>
    </div>
  );
}
