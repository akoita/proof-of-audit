"use client";

import { formatEth } from "../../lib/format";
import type {
  AuditRecord,
  AuditorServiceRecord,
  MarketplacePreviewResponse,
  PublicContractConfig,
  TargetComparisonResponse,
} from "../../lib/types";
import { TargetComparison } from "../target-comparison";

type MarketplaceViewProps = {
  contractAddress: string;
  bountyEth: string;
  protocolFeeEth: string;
  minimumStakeEth: string;
  whitelistMode: "open" | "allowlist";
  allowedServiceIds: string[];
  requiredIdentityServiceId: string;
  auditorServices: AuditorServiceRecord[];
  preview: MarketplacePreviewResponse | null;
  comparison: TargetComparisonResponse | null;
  selectedAudit: AuditRecord | null;
  config: PublicContractConfig | null;
  isPreviewLoaded: boolean;
  isComparisonLoaded: boolean;
  previewError: string | null;
  onContractAddressChange: (value: string) => void;
  onBountyEthChange: (value: string) => void;
  onProtocolFeeEthChange: (value: string) => void;
  onMinimumStakeEthChange: (value: string) => void;
  onWhitelistModeChange: (value: "open" | "allowlist") => void;
  onAllowedServiceIdsChange: (value: string[]) => void;
  onRequiredIdentityServiceIdChange: (value: string) => void;
  onSelectAudit: (audit: AuditRecord) => void;
};

export function MarketplaceView({
  contractAddress,
  bountyEth,
  protocolFeeEth,
  minimumStakeEth,
  whitelistMode,
  allowedServiceIds,
  requiredIdentityServiceId,
  auditorServices,
  preview,
  comparison,
  selectedAudit,
  config,
  isPreviewLoaded,
  isComparisonLoaded,
  previewError,
  onContractAddressChange,
  onBountyEthChange,
  onProtocolFeeEthChange,
  onMinimumStakeEthChange,
  onWhitelistModeChange,
  onAllowedServiceIdsChange,
  onRequiredIdentityServiceIdChange,
  onSelectAudit,
}: MarketplaceViewProps) {
  const identityOptions = auditorServices.filter(
    (service) => service.agent_id != null || service.agent_registry,
  );
  const matchingAuditors = preview?.auditor_matches.filter(
    (item) => item.eligibility.matches,
  ) ?? [];

  function toggleAllowedService(serviceId: string) {
    if (allowedServiceIds.includes(serviceId)) {
      onAllowedServiceIdsChange(
        allowedServiceIds.filter((existingId) => existingId !== serviceId),
      );
      return;
    }
    onAllowedServiceIdsChange([...allowedServiceIds, serviceId]);
  }

  return (
    <section className="workspace-grid">
      <div style={{ display: "grid", gap: 20, alignContent: "start" }}>
        <div className="card">
          <div className="card-body submit-panel">
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
              <h3 style={{ fontSize: "0.95rem", fontWeight: 700, display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontSize: "1.05rem" }}>🏪</span>
                Marketplace Request Draft
              </h3>
              <span className="badge" data-tone="neutral">API preview only</span>
            </div>

            <p className="notice-banner notice-banner-info">
              This tab previews marketplace request configuration and claim comparison. It does not create a chain-enforced request yet.
            </p>

            <div>
              <label className="section-label">Target Contract</label>
              <input
                className="input-field mono"
                value={contractAddress}
                onChange={(event) => onContractAddressChange(event.target.value)}
                placeholder="0x..."
                spellCheck={false}
              />
              <p className="muted" style={{ fontSize: "0.72rem", marginTop: 8 }}>
                Use the deployed contract address you want to open for bounty responses.
              </p>
            </div>

            <div className="marketplace-form-grid">
              <div>
                <label className="section-label">Bounty Pool (ETH)</label>
                <input
                  className="input-field"
                  inputMode="decimal"
                  value={bountyEth}
                  onChange={(event) => onBountyEthChange(event.target.value)}
                  placeholder="0.75"
                />
              </div>
              <div>
                <label className="section-label">Protocol Fee (ETH)</label>
                <input
                  className="input-field"
                  inputMode="decimal"
                  value={protocolFeeEth}
                  onChange={(event) => onProtocolFeeEthChange(event.target.value)}
                  placeholder="0.05"
                />
              </div>
            </div>

            <div>
              <label className="section-label">Minimum Stake Commitment (ETH)</label>
              <input
                className="input-field"
                inputMode="decimal"
                value={minimumStakeEth}
                onChange={(event) => onMinimumStakeEthChange(event.target.value)}
                placeholder="0.010"
              />
              <p className="muted" style={{ fontSize: "0.72rem", marginTop: 8 }}>
                Preview matching uses reported stake trail where available; absent stake telemetry is treated as approximate-only.
              </p>
            </div>

            <div>
              <label className="section-label">Whitelist Mode</label>
              <div className="marketplace-chip-row">
                <button
                  type="button"
                  className="badge"
                  data-tone={whitelistMode === "open" ? "confirmed" : "neutral"}
                  onClick={() => onWhitelistModeChange("open")}
                >
                  Open Request
                </button>
                <button
                  type="button"
                  className="badge"
                  data-tone={whitelistMode === "allowlist" ? "warning" : "neutral"}
                  onClick={() => onWhitelistModeChange("allowlist")}
                >
                  Allowlist Preview
                </button>
              </div>
            </div>

            {whitelistMode === "allowlist" ? (
              <div>
                <label className="section-label">Allowed Auditor Services</label>
                <div className="marketplace-checklist">
                  {auditorServices.map((service) => (
                    <label key={service.service_id} className="marketplace-check-item">
                      <input
                        type="checkbox"
                        checked={allowedServiceIds.includes(service.service_id)}
                        onChange={() => toggleAllowedService(service.service_id)}
                      />
                      <span>
                        <strong>{service.name}</strong>
                        <small>{service.execution_mode} · {service.publication_mode}</small>
                      </span>
                    </label>
                  ))}
                </div>
              </div>
            ) : null}

            <div>
              <label className="section-label">Required Registered Auditor Identity</label>
              <select
                className="input-field"
                value={requiredIdentityServiceId}
                onChange={(event) => onRequiredIdentityServiceIdChange(event.target.value)}
              >
                <option value="">Any registered auditor</option>
                {identityOptions.map((service) => (
                  <option key={service.service_id} value={service.service_id}>
                    {service.name}
                    {service.agent_id != null ? ` · agent ${service.agent_id}` : ""}
                  </option>
                ))}
              </select>
              <p className="muted" style={{ fontSize: "0.72rem", marginTop: 8 }}>
                Preview filtering keys off service ID, agent ID, and registry metadata already exposed by the auditor catalog.
              </p>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-body">
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
              <h3 style={{ fontSize: "0.95rem", fontWeight: 700 }}>Authority And Cost Breakdown</h3>
              <span className="badge" data-tone="confirmed">Chain + preview labels</span>
            </div>

            <div className="marketplace-stats-grid" style={{ marginTop: 16 }}>
              <div className="hash-card">
                <div className="hash-label">Chain-authoritative baseline</div>
                <div style={{ fontSize: "0.9rem", fontWeight: 700 }}>
                  {preview?.chain_context.network ?? config?.network ?? "Unavailable"}
                </div>
                <div className="muted" style={{ fontSize: "0.72rem", marginTop: 6, lineHeight: 1.6 }}>
                  Stake floor {formatEth(preview?.chain_context.required_stake_wei ?? config?.required_stake_wei ?? 0)}
                  <br />
                  Response window {Math.round((preview?.chain_context.challenge_window_seconds ?? config?.challenge_window_seconds ?? 0) / 3600)}h
                </div>
              </div>
              <div className="hash-card">
                <div className="hash-label">API preview cost</div>
                <div style={{ fontSize: "0.9rem", fontWeight: 700 }}>
                  {preview ? formatEth(preview.cost_breakdown.total_wei) : "Loading…"}
                </div>
                <div className="muted" style={{ fontSize: "0.72rem", marginTop: 6, lineHeight: 1.6 }}>
                  Bounty {preview ? formatEth(preview.cost_breakdown.bounty_wei) : "—"}
                  <br />
                  Protocol fee {preview ? formatEth(preview.cost_breakdown.protocol_fee_wei) : "—"}
                </div>
              </div>
            </div>

            {previewError ? (
              <p className="error-banner" style={{ marginTop: 16 }}>{previewError}</p>
            ) : !isPreviewLoaded ? (
              <p className="muted" style={{ fontSize: "0.78rem", marginTop: 16 }}>Refreshing marketplace preview…</p>
            ) : preview ? (
              <p className="muted" style={{ fontSize: "0.78rem", marginTop: 16, lineHeight: 1.6 }}>
                {preview.preview_disclaimer}
              </p>
            ) : null}
          </div>
        </div>
      </div>

      <div style={{ display: "grid", gap: 20, alignContent: "start" }}>
        <div className="card">
          <div className="card-body">
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
              <h3 style={{ fontSize: "0.95rem", fontWeight: 700 }}>Agent Eligibility Preview</h3>
              <span className="badge" data-tone="warning">
                {preview?.eligibility_summary.eligible_auditors ?? 0}/{preview?.eligibility_summary.total_auditors ?? auditorServices.length} approx. matches
              </span>
            </div>

            {preview ? (
              <>
                <p className="muted" style={{ fontSize: "0.78rem", marginTop: 12 }}>
                  {matchingAuditors.length > 0
                    ? `${matchingAuditors.length} auditors currently satisfy this preview request configuration.`
                    : "No auditors satisfy the current preview filters."}
                </p>
                <div className="marketplace-preview-list">
                  {preview.auditor_matches.map((item) => (
                    <div
                      key={item.service_id}
                      className="marketplace-preview-item"
                      data-match={item.eligibility.matches}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "flex-start" }}>
                        <div>
                          <div style={{ fontWeight: 700, fontSize: "0.84rem" }}>{item.name}</div>
                          <div className="muted" style={{ fontSize: "0.68rem", marginTop: 4 }}>
                            {item.service_id}
                            {item.agent_id != null ? ` · agent ${item.agent_id}` : ""}
                          </div>
                        </div>
                        <span className="badge" data-tone={item.eligibility.matches ? "confirmed" : "neutral"}>
                          {item.eligibility.matches ? "Preview match" : "Filtered out"}
                        </span>
                      </div>
                      <div className="marketplace-chip-row" style={{ marginTop: 10 }}>
                        {item.stake_preview_wei != null ? (
                          <span className="pill">Stake preview {formatEth(item.stake_preview_wei)}</span>
                        ) : (
                          <span className="pill">Stake preview unavailable</span>
                        )}
                        {item.reputation ? (
                          <span className="pill">Reputation {item.reputation.score}/100</span>
                        ) : null}
                      </div>
                      <p className="muted" style={{ fontSize: "0.72rem", marginTop: 10, lineHeight: 1.6 }}>
                        {item.eligibility.reasons.join(" ")}
                      </p>
                    </div>
                  ))}
                </div>
              </>
            ) : !isPreviewLoaded ? (
              <p className="muted" style={{ fontSize: "0.78rem", marginTop: 12 }}>Loading auditor preview…</p>
            ) : (
              <p className="muted" style={{ fontSize: "0.78rem", marginTop: 12 }}>Enter a target to preview eligible auditors.</p>
            )}
          </div>
        </div>

        <TargetComparison
          audit={selectedAudit}
          comparison={comparison}
          isLoaded={isComparisonLoaded}
          onSelect={onSelectAudit}
          title="Multi-Claim Comparison"
          emptyMessage="No submitted claims are available for this target yet."
          description="Response-window snapshot with side-by-side stake, severity, confidence, and disagreement signals."
          challengeWindowSeconds={preview?.chain_context.challenge_window_seconds ?? config?.challenge_window_seconds}
        />
      </div>
    </section>
  );
}
