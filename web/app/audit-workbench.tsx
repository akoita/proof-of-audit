"use client";

import { FormEvent, useEffect, useState, useTransition } from "react";
import { apiFetch, uploadSourceBundle } from "./lib/api";
import {
  formatEth,
  parseEthInputToWei,
  publishBlockedReason,
  relativeTimeLabel,
  submissionModeLabel,
  suggestedProofUriForBenchmark,
} from "./lib/format";
import type {
  AuditRecord,
  AuditorServiceRecord,
  DemoFixture,
  InputKind,
  MarketplacePreviewResponse,
  PublicContractConfig,
  TargetComparisonResponse,
} from "./lib/types";
import { Navbar } from "./components/navbar";
import { Sidebar } from "./components/sidebar";
import { PhaseStepper } from "./components/phase-stepper";
import { SubmitPanel } from "./components/submit-panel";
import { FixtureStrip } from "./components/fixture-strip";
import { AuditCard } from "./components/audit-card";
import { FindingsList } from "./components/findings-list";
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
import { DocsView } from "./components/views/docs-view";
import { MarketplaceView } from "./components/views/marketplace-view";

function preferredDemoFixture(fixtures: DemoFixture[]): DemoFixture | null {
  if (fixtures.length === 0) return null;
  return fixtures.find((f) => f.id === "clean-vault") ?? fixtures[0];
}

function supportsDemoFixtures(config: PublicContractConfig | null): boolean {
  const network = config?.network?.toLowerCase() ?? "";
  return (
    network.includes("anvil")
    || network.includes("localhost")
    || network.includes("local")
  );
}

function formatMediatedOnchainError(
  error: unknown,
  {
    action,
    amountWei,
    publicationMode,
    network,
  }: {
    action: "publish" | "challenge";
    amountWei: number;
    publicationMode: string | null | undefined;
    network: string | null | undefined;
  },
): string {
  const fallback =
    error instanceof Error
      ? error.message
      : `Failed to ${action}`;
  const normalized = fallback.toLowerCase();
  if (publicationMode !== "api_mediated" || !normalized.includes("insufficient funds")) {
    return fallback;
  }
  const networkLabel = network ?? "current";
  return `${action === "publish" ? "Publish" : "Challenge"} failed because this ${networkLabel} deployment uses an API signer and that backend wallet is underfunded. It must hold at least ${formatEth(amountWei)} plus gas. The connected browser wallet balance is not used for ${action} in api-mediated mode.`;
}

const VIEW_LABELS: Record<string, { eyebrow: string; title: string; desc: string }> = {
  workbench:  { eyebrow: "Workspace",       title: "Audit Workbench",    desc: "Upload smart contract artifacts or point to a mainnet address to initialize the forensic verification engine." },
  marketplace:{ eyebrow: "Marketplace",     title: "Bounty Marketplace", desc: "Preview bounty request configuration, V1 eligibility filters, and side-by-side claim comparison without overstating what the protocol enforces today." },
  published:  { eyebrow: "Published Claims", title: "Published",          desc: "Claims that have been staked and published on-chain. These can be challenged within the challenge window." },
  disputed:   { eyebrow: "Disputed Claims",  title: "Disputed",           desc: "Claims that have been challenged and are awaiting resolution through the advisory verifier or manual review." },
  reputation: { eyebrow: "Trust Network",    title: "Auditor Reputation", desc: "View trust scores, resolved challenges, and reputation metrics for auditor agents." },
  archive:    { eyebrow: "Archive",          title: "Archive",            desc: "Completed and resolved audit claims that have exited the challenge window." },
};

const VIEW_STATUS_MAP: Record<string, string[]> = {
  workbench:  [],
  marketplace: [],
  published:  ["published"],
  disputed:   ["challenged"],
  reputation: ["resolved"],
  archive:    ["resolved"],
};

function auditsForView(view: string, audits: AuditRecord[]): AuditRecord[] {
  const statuses = VIEW_STATUS_MAP[view] ?? [];
  if (statuses.length === 0) return audits;
  return audits.filter((audit) => statuses.includes(audit.status));
}

function selectAuditForView(
  view: string,
  audits: AuditRecord[],
  current: AuditRecord | null,
): AuditRecord | null {
  const scopedAudits = auditsForView(view, audits);
  if (scopedAudits.length === 0) return null;
  if (!current) return scopedAudits[0];
  return scopedAudits.find((audit) => audit.id === current.id) ?? scopedAudits[0];
}

export function AuditWorkbench() {
  /* ── sidebar state ────────────────────────────────────── */
  const [activeView, setActiveView] = useState("workbench");

  /* ── view filtering ──────────────────────────────────── */
  function handleViewChange(view: string) {
    setActiveView(view);
    setActiveAudit((current) => selectAuditForView(view, recentAudits, current));
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
  const [marketplaceContractAddress, setMarketplaceContractAddress] = useState("");
  const [marketplaceBountyEth, setMarketplaceBountyEth] = useState("0.750");
  const [marketplaceProtocolFeeEth, setMarketplaceProtocolFeeEth] = useState("0.050");
  const [marketplaceMinimumStakeEth, setMarketplaceMinimumStakeEth] = useState("");
  const [marketplaceWhitelistMode, setMarketplaceWhitelistMode] = useState<"open" | "allowlist">("open");
  const [marketplaceAllowedServiceIds, setMarketplaceAllowedServiceIds] = useState<string[]>([]);
  const [marketplaceRequiredIdentityServiceId, setMarketplaceRequiredIdentityServiceId] = useState("");

  /* ── data ───────────────────────────────────────────── */
  const [demoFixtures, setDemoFixtures] = useState<DemoFixture[]>([]);
  const [recentAudits, setRecentAudits] = useState<AuditRecord[]>([]);
  const [targetComparison, setTargetComparison] = useState<TargetComparisonResponse | null>(null);
  const [marketplacePreview, setMarketplacePreview] = useState<MarketplacePreviewResponse | null>(null);
  const [marketplaceComparison, setMarketplaceComparison] = useState<TargetComparisonResponse | null>(null);
  const [activeAudit, setActiveAudit] = useState<AuditRecord | null>(null);
  const [contractConfig, setContractConfig] = useState<PublicContractConfig | null>(null);
  const [auditorService, setAuditorService] = useState<AuditorServiceRecord | null>(null);
  const [auditorServices, setAuditorServices] = useState<AuditorServiceRecord[]>([]);
  const [selectedServiceId, setSelectedServiceId] = useState("");

  /* ── ui state ───────────────────────────────────────── */
  const [error, setError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [marketplaceError, setMarketplaceError] = useState<string | null>(null);
  const [isLoaded, setIsLoaded] = useState(false);
  const [isComparisonLoaded, setIsComparisonLoaded] = useState(false);
  const [isMarketplacePreviewLoaded, setIsMarketplacePreviewLoaded] = useState(false);
  const [isMarketplaceComparisonLoaded, setIsMarketplaceComparisonLoaded] = useState(false);
  const [activeAction, setActiveAction] = useState<string | null>(null);
  const [isUploadingSourceBundle, setIsUploadingSourceBundle] = useState(false);
  const [isPending, startTransition] = useTransition();

  const selectedFixture =
    demoFixtures.find((f) => f.id === selectedFixtureId) ??
    demoFixtures.find((f) => f.address === contractAddress) ??
    undefined;
  const publishStake = contractConfig?.required_stake_wei ?? 10_000_000_000_000_000;
  const challengeBond = contractConfig?.required_challenge_bond_wei ?? 5_000_000_000_000_000;
  const systemStatus = !isLoaded
    ? "Loading workspace"
    : loadError || error
      ? "Attention needed"
      : isPending
        ? "Refreshing data"
        : contractConfig?.deployment_ready === false
          ? "Read-only config"
          : "Connected";
  const workspaceMeta = activeAudit
    ? `ACTIVE AUDIT: ${relativeTimeLabel(activeAudit.created_at)}`
    : isLoaded
      ? `AUDITS LOADED: ${recentAudits.length}`
      : "LOADING WORKSPACE";
  const footerNetwork = contractConfig
    ? `${contractConfig.network} · Chain ${contractConfig.chain_id}`
    : "Network unavailable";
  const demoFixturesEnabled = supportsDemoFixtures(contractConfig);
  const selectedAuditorService =
    auditorServices.find((service) => service.service_id === selectedServiceId) ??
    activeAudit?.auditor_service ??
    auditorService;

  /* ── view-filtered audits ────────────────────────────── */
  const filteredAudits = auditsForView(activeView, recentAudits);
  const scopedActiveAudit =
    activeView === "workbench"
      ? activeAudit
      : selectAuditForView(activeView, recentAudits, activeAudit);

  /* ── data loading ───────────────────────────────────── */
  useEffect(() => {
    startTransition(() => void loadWorkbench());
  }, []);

  useEffect(() => {
    setActiveAudit((current) => {
      const next = selectAuditForView(activeView, recentAudits, current);
      if (next?.id === current?.id) return current;
      if (!next && !current) return current;
      return next;
    });
  }, [activeView, recentAudits]);

  useEffect(() => {
    if (!activeAudit?.contract_address) {
      setTargetComparison(null);
      setIsComparisonLoaded(false);
      return;
    }
    startTransition(() => void loadTargetComparison(activeAudit.contract_address));
  }, [activeAudit?.id, activeAudit?.contract_address]);

  useEffect(() => {
    if (!demoFixturesEnabled && submissionMode === "demo_fixture") {
      setSubmissionMode("deployed_address");
      setSelectedFixtureId("");
    }
  }, [demoFixturesEnabled, submissionMode]);

  useEffect(() => {
    const candidate = activeAudit?.contract_address ?? contractAddress;
    if (!candidate) {
      return;
    }
    setMarketplaceContractAddress((current) => current || candidate);
  }, [activeAudit?.contract_address, contractAddress]);

  useEffect(() => {
    if (!contractConfig?.required_stake_wei) {
      return;
    }
    setMarketplaceMinimumStakeEth((current) => {
      if (current.trim().length > 0) {
        return current;
      }
      return (contractConfig.required_stake_wei / 1e18).toFixed(3);
    });
  }, [contractConfig?.required_stake_wei]);

  useEffect(() => {
    const trimmedContractAddress = marketplaceContractAddress.trim();
    if (!trimmedContractAddress) {
      setMarketplacePreview(null);
      setMarketplaceComparison(null);
      setMarketplaceError(null);
      setIsMarketplacePreviewLoaded(true);
      setIsMarketplaceComparisonLoaded(true);
      return;
    }

    const abortController = new AbortController();
    const timeoutId = window.setTimeout(() => {
      startTransition(() => {
        void loadMarketplacePreview(trimmedContractAddress, abortController.signal);
        void loadMarketplaceComparison(trimmedContractAddress, abortController.signal);
      });
    }, 200);

    return () => {
      window.clearTimeout(timeoutId);
      abortController.abort();
    };
  }, [
    marketplaceAllowedServiceIds,
    marketplaceBountyEth,
    marketplaceContractAddress,
    marketplaceMinimumStakeEth,
    marketplaceProtocolFeeEth,
    marketplaceRequiredIdentityServiceId,
    marketplaceWhitelistMode,
  ]);

  async function loadWorkbench() {
    setLoadError(null);
    try {
      const [auditPayload, fixturePayload, configPayload, auditorPayload, auditorsPayload] = await Promise.all([
        apiFetch<{ items: AuditRecord[] }>("/audits"),
        apiFetch<{ items: DemoFixture[] }>("/fixtures"),
        apiFetch<PublicContractConfig>("/config"),
        apiFetch<AuditorServiceRecord>("/auditor"),
        apiFetch<{ items: AuditorServiceRecord[] }>("/auditors"),
      ]);
      const allowDemoFixtures = supportsDemoFixtures(configPayload);
      setRecentAudits(auditPayload.items);
      setDemoFixtures(fixturePayload.items);
      setContractConfig(configPayload);
      setAuditorService(auditorPayload);
      setAuditorServices(auditorsPayload.items);
      setSelectedServiceId((current) => {
        if (current) return current;
        if (auditPayload.items[0]?.auditor_service?.service_id) {
          return auditPayload.items[0].auditor_service.service_id;
        }
        return configPayload.auditor_service.service_id;
      });
      if (auditPayload.items.length > 0) {
        setActiveAudit((current) => current ?? selectAuditForView(activeView, auditPayload.items, null));
      }
      if (allowDemoFixtures && fixturePayload.items.length > 0 && !selectedFixtureId) {
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

  async function loadMarketplacePreview(addr: string, signal?: AbortSignal) {
    setIsMarketplacePreviewLoaded(false);
    setMarketplaceError(null);
    try {
      setMarketplacePreview(await apiFetch<MarketplacePreviewResponse>("/marketplace/preview", {
        method: "POST",
        signal,
        body: JSON.stringify({
          contract_address: addr,
          bounty_wei: parseEthInputToWei(marketplaceBountyEth),
          protocol_fee_wei: parseEthInputToWei(marketplaceProtocolFeeEth),
          filters: {
            minimum_stake_wei: parseEthInputToWei(marketplaceMinimumStakeEth),
            whitelist_mode: marketplaceWhitelistMode,
            allowed_service_ids: marketplaceAllowedServiceIds,
            required_identity_service_id: marketplaceRequiredIdentityServiceId || null,
          },
        }),
      }));
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        return;
      }
      setMarketplacePreview(null);
      setMarketplaceError(err instanceof Error ? err.message : "Failed to load marketplace preview");
    } finally {
      if (signal?.aborted) {
        return;
      }
      setIsMarketplacePreviewLoaded(true);
    }
  }

  async function loadMarketplaceComparison(addr: string, signal?: AbortSignal) {
    setIsMarketplaceComparisonLoaded(false);
    try {
      setMarketplaceComparison(await apiFetch<TargetComparisonResponse>(`/targets/${addr}/comparison`, { signal }));
    } catch {
      if (signal?.aborted) {
        return;
      }
      setMarketplaceComparison(null);
    } finally {
      if (signal?.aborted) {
        return;
      }
      setIsMarketplaceComparisonLoaded(true);
    }
  }

  /* ── actions ────────────────────────────────────────── */
  function syncAudit(next: AuditRecord) {
    setActiveAudit(next);
    setSubmissionMode(
      !demoFixturesEnabled && next.submission.input_kind === "demo_fixture"
        ? "deployed_address"
        : next.submission.input_kind,
    );
    setSelectedServiceId(next.submission.service_id ?? next.auditor_service.service_id);
    setContractAddress(next.submission.contract_address ?? next.contract_address);
    setSelectedFixtureId(demoFixturesEnabled ? (next.submission.fixture_id ?? "") : "");
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
          const effectiveSubmissionMode =
            !demoFixturesEnabled && submissionMode === "demo_fixture"
              ? "deployed_address"
              : submissionMode;
          const payload =
            effectiveSubmissionMode === "demo_fixture"
                ? {
                    input_kind: "demo_fixture",
                    service_id: selectedServiceId || contractConfig?.auditor_service.service_id,
                    fixture_id: selectedFixtureId,
                    chain_id: contractConfig?.chain_id,
                    entry_contract: entryContract || selectedFixture?.entry_contract,
                  submitted_by: "web-demo",
                }
                : effectiveSubmissionMode === "source_bundle"
                  ? {
                      input_kind: "source_bundle",
                      service_id: selectedServiceId || contractConfig?.auditor_service.service_id,
                      source_bundle_uri: sourceBundleUri,
                      source_bundle_label: sourceBundleLabel || undefined,
                      entry_contract: entryContract || undefined,
                    submitted_by: "web-demo",
                  }
                  : {
                      input_kind: "deployed_address",
                      service_id: selectedServiceId || contractConfig?.auditor_service.service_id,
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

  async function handleSourceBundleFileSelect(file: File) {
    const suffix = file.name.split(".").pop()?.toLowerCase();
    if (!suffix || !["sol", "zip"].includes(suffix)) {
      setError("Only .zip and .sol files are supported for source bundle uploads.");
      return;
    }

    setError(null);
    setSubmissionMode("source_bundle");
    setIsUploadingSourceBundle(true);
    try {
      const upload = await uploadSourceBundle(file);
      setSourceBundleUri(upload.source_bundle_uri);
      setSourceBundleLabel(upload.source_bundle_label ?? "");
      setEntryContract((current) => upload.entry_contract ?? current);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to upload source bundle");
    } finally {
      setIsUploadingSourceBundle(false);
    }
  }

  async function handlePublish() {
    if (!activeAudit) return;
    const blockedReason = publishBlockedReason(activeAudit);
    if (blockedReason) {
      setError(blockedReason);
      return;
    }
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
          setError(
            formatMediatedOnchainError(e, {
              action: "publish",
              amountWei: publishStake,
              publicationMode: selectedAuditorService?.publication_mode,
              network: contractConfig?.network,
            }),
          );
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
          setError(
            formatMediatedOnchainError(e, {
              action: "challenge",
              amountWei: challengeBond,
              publicationMode: selectedAuditorService?.publication_mode,
              network: contractConfig?.network,
            }),
          );
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
                <span>{systemStatus}</span>
              </div>
            </div>
            <h1>{VIEW_LABELS[activeView]?.title ?? "Audit Workbench"}</h1>
            <p>{VIEW_LABELS[activeView]?.desc ?? "Upload smart contract artifacts or point to a mainnet address to initialize the forensic verification engine."}</p>
          </div>
          <div className="page-meta-badge">
            ⏱ {workspaceMeta}
          </div>
        </div>

        {/* Phase stepper — workbench only */}
        {activeView === "workbench" ? <PhaseStepper audit={activeAudit} /> : null}

        {/* ── Demo Fixtures — workbench only ── */}
        {activeView === "workbench" && demoFixturesEnabled ? (
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
        ) : null}

        {/* ── View-specific content ── */}
        {activeView === "workbench" ? (
          <>
            {/* Main workspace: submission + audit report */}
            <section id="workspace-section" className="workspace-grid">
              {/* Left column: submit + meta */}
              <div id="submit-section" style={{ display: "grid", gap: 20, alignContent: "start" }}>
                <SubmitPanel
                  submissionMode={submissionMode}
                  allowDemoFixtures={demoFixturesEnabled}
                  contractAddress={contractAddress}
                  selectedFixtureId={selectedFixtureId}
                  auditorServices={auditorServices}
                  selectedServiceId={selectedServiceId}
                  selectedAuditorService={selectedAuditorService}
                  entryContract={entryContract}
                  sourceBundleUri={sourceBundleUri}
                  sourceBundleLabel={sourceBundleLabel}
                  selectedFixture={selectedFixture}
                  isPending={isPending || isUploadingSourceBundle}
                  activeAction={activeAction}
                  config={contractConfig}
                  onModeChange={setSubmissionMode}
                  onSelectedServiceIdChange={setSelectedServiceId}
                  onContractAddressChange={setContractAddress}
                  onEntryContractChange={setEntryContract}
                  onSourceBundleUriChange={setSourceBundleUri}
                  onSourceBundleLabelChange={setSourceBundleLabel}
                  onSourceBundleFileSelect={handleSourceBundleFileSelect}
                  isUploadingSourceBundle={isUploadingSourceBundle}
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
                    <div className="meta-value">{submissionModeLabel(submissionMode)}</div>
                  </div>
                  <div className="meta-bento-item">
                    <div className="meta-label">Auditor</div>
                    <div className="meta-value">{selectedAuditorService?.name ?? "Unavailable"}</div>
                  </div>
                  <div className="meta-bento-item">
                    <div className="meta-label">Revision</div>
                    <div className="meta-value">
                      {activeAudit?.agent.version ?? contractConfig?.auditor?.version ?? "Unavailable"}
                    </div>
                  </div>
                </div>

                {/* Agent sidebar cards */}
                <div id="agent-info">
                  <AgentSidebar
                    config={contractConfig}
                    auditorService={activeAudit?.auditor_service ?? selectedAuditorService ?? auditorService}
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
                    <FindingsList findings={activeAudit.report.findings} />
                    <ActionsPanel
                      audit={activeAudit}
                      config={contractConfig}
                      publicationMode={
                        activeAudit.auditor_service.publication_mode ??
                        selectedAuditorService?.publication_mode
                      }
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


          </>
        ) : activeView === "marketplace" ? (
          <MarketplaceView
            contractAddress={marketplaceContractAddress}
            bountyEth={marketplaceBountyEth}
            protocolFeeEth={marketplaceProtocolFeeEth}
            minimumStakeEth={marketplaceMinimumStakeEth}
            whitelistMode={marketplaceWhitelistMode}
            allowedServiceIds={marketplaceAllowedServiceIds}
            requiredIdentityServiceId={marketplaceRequiredIdentityServiceId}
            auditorServices={auditorServices}
            preview={marketplacePreview}
            comparison={marketplaceComparison}
            selectedAudit={
              activeAudit?.contract_address.toLowerCase() === marketplaceContractAddress.trim().toLowerCase()
                ? activeAudit
                : null
            }
            config={contractConfig}
            isPreviewLoaded={isMarketplacePreviewLoaded}
            isComparisonLoaded={isMarketplaceComparisonLoaded}
            previewError={marketplaceError}
            onContractAddressChange={setMarketplaceContractAddress}
            onBountyEthChange={setMarketplaceBountyEth}
            onProtocolFeeEthChange={setMarketplaceProtocolFeeEth}
            onMinimumStakeEthChange={setMarketplaceMinimumStakeEth}
            onWhitelistModeChange={setMarketplaceWhitelistMode}
            onAllowedServiceIdsChange={setMarketplaceAllowedServiceIds}
            onRequiredIdentityServiceIdChange={setMarketplaceRequiredIdentityServiceId}
            onSelectAudit={syncAudit}
          />
        ) : activeView === "published" ? (
          scopedActiveAudit ? (
            <PublishedView audit={scopedActiveAudit} allAudits={filteredAudits} onSelect={syncAudit} />
          ) : (
            <div className="card"><div className="empty-panel"><strong>No published claims found</strong><p className="muted">Publish an audit claim from the workbench to see it here.</p></div></div>
          )
        ) : activeView === "disputed" ? (
          scopedActiveAudit ? (
            <DisputedView audit={scopedActiveAudit} allAudits={filteredAudits} onSelect={syncAudit} />
          ) : (
            <div className="card"><div className="empty-panel"><strong>No disputed claims</strong><p className="muted">No claims are currently under dispute.</p></div></div>
          )
        ) : activeView === "reputation" ? (
          <ReputationView
            config={contractConfig}
            audits={recentAudits}
            auditorService={activeAudit?.auditor_service ?? selectedAuditorService ?? auditorService}
          />
        ) : activeView === "archive" ? (
          <ArchiveView audits={filteredAudits} onSelect={syncAudit} />
        ) : activeView === "docs" ? (
          <DocsView />
        ) : null}

        {/* Footer data */}
        <div className="footer-data">
          <div className="footer-item">🗂 Audits: {recentAudits.length}</div>
          <div className="footer-item">🧪 Fixtures: {demoFixtures.length}</div>
          <div className="footer-item">⛓ {footerNetwork}</div>
        </div>
      </main>
    </div>
  );
}
