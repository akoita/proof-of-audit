"use client";

import type { AuditorServiceRecord, PublicContractConfig } from "../lib/types";
import {
  addressUrl,
  agentVersionLabel,
  formatEth,
  formatIdentitySource,
  formatValidationSource,
  formatWindow,
  isExplorerLink,
  reputationLabel,
  shortenHex,
  titleCase,
} from "../lib/format";

type AgentSidebarProps = {
  config: PublicContractConfig | null;
  auditorService: AuditorServiceRecord | null;
  publishStake: number;
  challengeBond: number;
};

export function AgentSidebar({
  config,
  auditorService,
  publishStake,
  challengeBond,
}: AgentSidebarProps) {
  const reputation = auditorService?.reputation ?? config?.auditor?.reputation;
  const score = reputation?.score ?? 0;

  return (
    <div className="agent-sidebar">
      {/* Agent identity card */}
      <div className="agent-identity-card">
        <div className="agent-avatar">
          <svg viewBox="0 0 80 80" className="reputation-ring">
            <circle cx="40" cy="40" r="34" fill="none" stroke="var(--line)" strokeWidth="5" />
            <circle
              cx="40"
              cy="40"
              r="34"
              fill="none"
              stroke={
                score >= 70 ? "var(--tone-confirmed)" :
                score >= 40 ? "var(--tone-warning)" :
                "var(--tone-danger)"
              }
              strokeWidth="5"
              strokeLinecap="round"
              strokeDasharray={`${score * 2.136} 214`}
              transform="rotate(-90 40 40)"
              className="reputation-fill"
            />
          </svg>
          <div className="reputation-score">
            <strong>{score}</strong>
            <span>/100</span>
          </div>
        </div>
        <div className="agent-info">
          <strong>{agentVersionLabel(config?.auditor)}</strong>
          <span className="reputation-band" data-band={reputation?.band ?? "provisional"}>
            {reputation ? titleCase(reputation.band) : "Loading"}
          </span>
        </div>
      </div>

      {/* Reputation stats */}
      {reputation ? (
        <div className="reputation-stats">
          <div>
            <span>{reputation.challenge_rejected_count}</span>
            <em>Rejected</em>
          </div>
          <div>
            <span>{reputation.challenge_upheld_count}</span>
            <em>Upheld</em>
          </div>
          <div>
            <span>{reputation.resolved_challenge_count}</span>
            <em>Resolved</em>
          </div>
        </div>
      ) : null}

      {/* Economics */}
      <div className="economics-card">
        <p className="card-label">Economic parameters</p>
        <div className="econ-grid">
          <div><span>Stake</span><strong>{formatEth(publishStake)}</strong></div>
          <div><span>Bond</span><strong>{formatEth(challengeBond)}</strong></div>
          <div>
            <span>Window</span>
            <strong>{config ? formatWindow(config.challenge_window_seconds) : "—"}</strong>
          </div>
          <div>
            <span>Network</span>
            <strong>{config?.network ?? "—"}</strong>
          </div>
        </div>
      </div>

      {/* Service discovery */}
      <div className="service-card">
        <p className="card-label">Service discovery</p>
        <strong>
          {auditorService?.name ?? config?.auditor?.name ?? "loading"}
        </strong>
        <p className="muted">
          {auditorService
            ? `${auditorService.service_id} · ${titleCase(auditorService.capability)}`
            : "Loading agent identity"}
        </p>
        <p className="muted">
          {config?.auditor?.description ?? "Agent profile loading."}
        </p>
        {auditorService ? (
          <div className="discovery-meta">
            <span>{titleCase(auditorService.registration_kind)}</span>
            <span title={auditorService.manifest_hash}>
              {shortenHex(auditorService.manifest_hash, 10, 8)}
            </span>
            {auditorService.agent_id && auditorService.agent_registry ? (
              <span title={auditorService.agent_registry}>
                Agent #{auditorService.agent_id} @ {shortenHex(auditorService.agent_registry, 10, 8)}
              </span>
            ) : null}
            {auditorService.identity_source ? (
              <span>{formatIdentitySource(auditorService.identity_source)}</span>
            ) : null}
          </div>
        ) : null}
      </div>

      {/* ERC-8004 */}
      <div className="service-card">
        <p className="card-label">ERC-8004 alignment</p>
        <strong>
          {auditorService?.identity_source
            ? formatIdentitySource(auditorService.identity_source)
            : "Loading"}
        </strong>
        <p className="muted">
          Identity and validation follow ERC-8004-style public records.
        </p>
        {auditorService ? (
          <div className="discovery-meta">
            {auditorService.validation_registry_address ? (
              <span title={auditorService.validation_registry_address}>
                Validation: {formatValidationSource(auditorService.validation_source)} @{" "}
                {shortenHex(auditorService.validation_registry_address, 10, 8)}
              </span>
            ) : null}
          </div>
        ) : null}
      </div>

      {/* Registry contract */}
      {config?.contract_address ? (
        <div className="service-card">
          <p className="card-label">Registry contract</p>
          <strong title={config.contract_address}>
            {shortenHex(config.contract_address, 10, 8)}
          </strong>
          {addressUrl(config.explorer_base_url, config.contract_address) ? (
            <a
              href={addressUrl(config.explorer_base_url, config.contract_address) ?? undefined}
              target="_blank"
              rel="noreferrer"
              className="contract-link"
            >
              View contract ↗
            </a>
          ) : (
            <span className="muted">Local RPC — no explorer link.</span>
          )}
        </div>
      ) : null}
    </div>
  );
}
