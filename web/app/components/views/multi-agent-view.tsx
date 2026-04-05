"use client";

import { useMemo, useState } from "react";
import type { AuditRecord, AuditorReputation } from "../../lib/types";
import {
  severityRankLabel,
  formatEth,
  reputationLabel,
  titleCase,
} from "../../lib/format";

type MultiAgentViewProps = {
  audits: AuditRecord[];
  onSelect: (audit: AuditRecord) => void;
};

/* ── Helpers ── */

type AgentLane = {
  serviceId: string;
  name: string;
  reputation: AuditorReputation | null;
  audits: AuditRecord[];
};

type FindingKey = string;

function findingKey(title: string, severity: string, category: string): FindingKey {
  return `${severity}::${category}::${title}`.toLowerCase();
}

function severityColor(rank: number): string {
  switch (rank) {
    case 4: return "var(--error)";
    case 3: return "var(--error)";
    case 2: return "var(--tertiary)";
    case 1: return "var(--secondary)";
    default: return "var(--on-surface-variant)";
  }
}

function reputationRingColor(score: number): string {
  if (score >= 70) return "var(--secondary)";
  if (score >= 40) return "var(--tertiary)";
  return "var(--error)";
}

/* ── Component ── */

export function MultiAgentView({ audits, onSelect }: MultiAgentViewProps) {
  const [selectedContract, setSelectedContract] = useState<string | null>(null);
  const [filterAgentIds, setFilterAgentIds] = useState<Set<string>>(new Set());

  /* Group by contract address */
  const contractGroups = useMemo(() => {
    const map = new Map<string, AuditRecord[]>();
    for (const audit of audits) {
      const key = audit.contract_address || audit.submission.fixture_id || audit.id;
      const list = map.get(key) ?? [];
      list.push(audit);
      map.set(key, list);
    }
    return map;
  }, [audits]);

  const contractKeys = useMemo(() => Array.from(contractGroups.keys()), [contractGroups]);
  const activeContractKey = selectedContract ?? contractKeys[0] ?? null;
  const contractAudits = activeContractKey ? (contractGroups.get(activeContractKey) ?? []) : [];

  /* Build agent lanes */
  const lanes: AgentLane[] = useMemo(() => {
    const laneMap = new Map<string, AgentLane>();
    for (const audit of contractAudits) {
      const serviceId = audit.auditor_service?.service_id ?? audit.agent?.id ?? audit.id;
      const existing = laneMap.get(serviceId);
      if (existing) {
        existing.audits.push(audit);
      } else {
        laneMap.set(serviceId, {
          serviceId,
          name: audit.agent?.name ?? serviceId,
          reputation: audit.auditor_service?.reputation ?? audit.agent?.reputation ?? null,
          audits: [audit],
        });
      }
    }
    return Array.from(laneMap.values());
  }, [contractAudits]);

  const visibleLanes = filterAgentIds.size > 0
    ? lanes.filter((lane) => filterAgentIds.has(lane.serviceId))
    : lanes;

  /* Compute global finding set for overlap analysis */
  const allFindingKeys = useMemo(() => {
    const keys = new Set<FindingKey>();
    for (const lane of visibleLanes) {
      for (const audit of lane.audits) {
        for (const finding of audit.report.findings) {
          keys.add(findingKey(finding.title, finding.severity, finding.category));
        }
      }
    }
    return keys;
  }, [visibleLanes]);

  /* For each finding key, count how many agents found it */
  const findingAgreement = useMemo(() => {
    const counts = new Map<FindingKey, number>();
    for (const key of allFindingKeys) {
      let agentCount = 0;
      for (const lane of visibleLanes) {
        const hasIt = lane.audits.some((audit) =>
          audit.report.findings.some((f) => findingKey(f.title, f.severity, f.category) === key),
        );
        if (hasIt) agentCount += 1;
      }
      counts.set(key, agentCount);
    }
    return counts;
  }, [allFindingKeys, visibleLanes]);

  const totalAgents = visibleLanes.length;

  /* contract label */
  function contractLabel(key: string): string {
    const auditsForKey = contractGroups.get(key) ?? [];
    const fixture = auditsForKey[0]?.submission?.fixture_id;
    if (fixture) return titleCase(fixture.replace(/-/g, " "));
    if (key.startsWith("0x")) return `${key.slice(0, 10)}…${key.slice(-6)}`;
    return key;
  }

  /* Toggle agent filter */
  function toggleAgent(serviceId: string) {
    setFilterAgentIds((prev) => {
      const next = new Set(prev);
      if (next.has(serviceId)) {
        next.delete(serviceId);
      } else {
        next.add(serviceId);
      }
      return next;
    });
  }

  const agreedCount = Array.from(findingAgreement.values()).filter((c) => c === totalAgents).length;
  const divergentCount = Array.from(findingAgreement.values()).filter((c) => c < totalAgents && c > 0).length;

  return (
    <div className="multi-agent-dashboard" id="multi-agent-dashboard">
      {/* ── Contract selector strip ── */}
      {contractKeys.length > 1 ? (
        <div className="ma-contract-strip">
          <span className="ma-contract-strip-label">Target Contract</span>
          <div className="ma-contract-strip-items">
            {contractKeys.map((key) => (
              <button
                key={key}
                type="button"
                className="ma-contract-chip"
                data-active={key === activeContractKey}
                onClick={() => setSelectedContract(key)}
              >
                {contractLabel(key)}
                <span className="ma-contract-chip-count">
                  {contractGroups.get(key)?.length ?? 0}
                </span>
              </button>
            ))}
          </div>
        </div>
      ) : null}

      {/* ── Agent filter dropdown ── */}
      <div className="ma-controls">
        <div className="ma-agent-filter">
          <span className="ma-filter-label">Agents</span>
          <div className="ma-filter-chips">
            {lanes.map((lane) => (
              <button
                key={lane.serviceId}
                type="button"
                className="ma-filter-chip"
                data-active={filterAgentIds.size === 0 || filterAgentIds.has(lane.serviceId)}
                onClick={() => toggleAgent(lane.serviceId)}
              >
                <span className="ma-filter-chip-dot" style={{
                  background: reputationRingColor(lane.reputation?.score ?? 0),
                }} />
                {lane.name}
              </button>
            ))}
            {filterAgentIds.size > 0 ? (
              <button
                type="button"
                className="ma-filter-chip ma-filter-reset"
                onClick={() => setFilterAgentIds(new Set())}
              >
                Show All
              </button>
            ) : null}
          </div>
        </div>

        {/* ── Agreement summary ── */}
        <div className="ma-agreement-summary">
          <span className="ma-agreement-badge ma-badge-agreed">
            ✓ {agreedCount} agreed
          </span>
          <span className="ma-agreement-badge ma-badge-divergent">
            ⚡ {divergentCount} divergent
          </span>
          <span className="ma-agreement-badge ma-badge-total">
            {allFindingKeys.size} total findings
          </span>
        </div>
      </div>

      {/* ── Multi-lane grid ── */}
      {visibleLanes.length === 0 ? (
        <div className="card">
          <div className="empty-panel">
            <strong>No agent claims found</strong>
            <p className="muted">
              Submit audits from multiple agents to see side-by-side claim comparison.
            </p>
          </div>
        </div>
      ) : (
        <div
          className="ma-lane-grid"
          style={{ gridTemplateColumns: `repeat(${visibleLanes.length}, 1fr)` }}
        >
          {visibleLanes.map((lane) => {
            const bestAudit = lane.audits[0]; // most recent
            const rep = lane.reputation;
            const score = rep?.score ?? 0;
            const ringColor = reputationRingColor(score);
            const circumference = 2 * Math.PI * 24;
            const dashArray = `${(score / 100) * circumference} ${circumference}`;
            const maxSev = Math.max(...lane.audits.map((a) => a.report.max_severity), 0);
            const totalFindings = lane.audits.reduce(
              (sum, a) => sum + a.report.finding_count,
              0,
            );

            return (
              <div key={lane.serviceId} className="ma-lane">
                {/* Agent header */}
                <div className="ma-lane-header">
                  <div className="ma-lane-avatar" style={{ borderColor: ringColor }}>
                    {lane.name.charAt(0).toUpperCase()}
                  </div>
                  <div className="ma-lane-identity">
                    <div className="ma-lane-name">{lane.name}</div>
                    <div className="ma-lane-service">{lane.serviceId}</div>
                  </div>
                </div>

                {/* Reputation mini ring */}
                <div className="ma-lane-reputation">
                  <div className="ma-mini-ring">
                    <svg viewBox="0 0 56 56">
                      <circle className="ring-bg" cx="28" cy="28" r="24" />
                      <circle
                        className="ring-fill"
                        cx="28" cy="28" r="24"
                        strokeDasharray={dashArray}
                        transform="rotate(-90 28 28)"
                        style={{ stroke: ringColor }}
                      />
                    </svg>
                    <span className="ma-mini-ring-value">{score}</span>
                  </div>
                  <span className="ma-reputation-band" style={{ color: ringColor }}>
                    {rep?.band ? titleCase(rep.band) : "Unranked"}
                  </span>
                </div>

                {/* Stats row */}
                <div className="ma-lane-stats">
                  <div className="ma-stat">
                    <span className="ma-stat-val">{totalFindings}</span>
                    <span className="ma-stat-label">Findings</span>
                  </div>
                  <div className="ma-stat">
                    <span className="ma-stat-val" style={{ color: severityColor(maxSev) }}>
                      {severityRankLabel(maxSev)}
                    </span>
                    <span className="ma-stat-label">Max Severity</span>
                  </div>
                  <div className="ma-stat">
                    <span className="ma-stat-val">
                      {bestAudit?.onchain ? "✓" : "—"}
                    </span>
                    <span className="ma-stat-label">Published</span>
                  </div>
                </div>

                {/* Findings list with agreement badges */}
                <div className="ma-lane-findings">
                  {lane.audits.flatMap((audit) =>
                    audit.report.findings.map((f) => {
                      const fKey = findingKey(f.title, f.severity, f.category);
                      const agreeCount = findingAgreement.get(fKey) ?? 0;
                      const isUniversal = agreeCount === totalAgents;
                      const isUnique = agreeCount === 1;

                      return (
                        <button
                          key={`${audit.id}-${f.finding_id}`}
                          type="button"
                          className="ma-finding-row"
                          data-agreement={isUniversal ? "agreed" : isUnique ? "unique" : "partial"}
                          onClick={() => onSelect(audit)}
                        >
                          <div className="ma-finding-header">
                            <span
                              className="ma-finding-severity"
                              style={{ color: severityColor(
                                f.severity === "critical" ? 4
                                  : f.severity === "high" ? 3
                                  : f.severity === "medium" ? 2
                                  : f.severity === "low" ? 1
                                  : 0,
                              ) }}
                            >
                              {titleCase(f.severity)}
                            </span>
                            <span className={`ma-finding-agree-badge ${
                              isUniversal ? "ma-badge-agreed" : isUnique ? "ma-badge-unique" : "ma-badge-partial"
                            }`}>
                              {isUniversal
                                ? "✓ All agree"
                                : isUnique
                                  ? "⚡ Unique"
                                  : `${agreeCount}/${totalAgents}`}
                            </span>
                          </div>
                          <div className="ma-finding-title">{f.title}</div>
                          {f.affected_function ? (
                            <div className="ma-finding-func mono">{f.affected_function}</div>
                          ) : null}
                        </button>
                      );
                    }),
                  )}
                  {lane.audits.every((a) => a.report.findings.length === 0) ? (
                    <div className="ma-finding-empty">No findings</div>
                  ) : null}
                </div>

                {/* Challenge indicator */}
                {lane.audits.some((a) => a.challenge) ? (
                  <div className="ma-lane-challenge">
                    <span className="ma-challenge-icon">⚖</span>
                    <span>
                      {lane.audits.filter((a) => a.challenge).length} challenge(s) active
                    </span>
                  </div>
                ) : null}

                {/* On-chain info */}
                {bestAudit?.onchain ? (
                  <div className="ma-lane-onchain">
                    <span className="ma-onchain-label">Staked</span>
                    <span className="ma-onchain-value">
                      {formatEth(bestAudit.onchain.stake_wei)}
                    </span>
                  </div>
                ) : null}

                {/* Click to view full audit */}
                <button
                  type="button"
                  className="ma-lane-action"
                  onClick={() => onSelect(bestAudit)}
                >
                  View Full Report →
                </button>
              </div>
            );
          })}
        </div>
      )}

      {/* ── Finding agreement breakdown ── */}
      {allFindingKeys.size > 0 ? (
        <div className="ma-agreement-breakdown">
          <h3 className="ma-section-title">
            <span>🔍</span> Finding Agreement Matrix
          </h3>
          <div className="ma-agreement-table-wrap">
            <table className="ma-agreement-table">
              <thead>
                <tr>
                  <th>Finding</th>
                  <th>Severity</th>
                  {visibleLanes.map((lane) => (
                    <th key={lane.serviceId}>{lane.name.split(" ")[0]}</th>
                  ))}
                  <th>Agreement</th>
                </tr>
              </thead>
              <tbody>
                {Array.from(allFindingKeys).map((fKey) => {
                  const parts = fKey.split("::");
                  const severity = parts[0] ?? "";
                  const title = parts[2] ?? fKey;
                  const agreeCount = findingAgreement.get(fKey) ?? 0;
                  const isUniversal = agreeCount === totalAgents;

                  return (
                    <tr key={fKey} data-agreement={isUniversal ? "agreed" : "divergent"}>
                      <td className="ma-table-finding">{titleCase(title)}</td>
                      <td>
                        <span style={{ color: severityColor(
                          severity === "critical" ? 4
                            : severity === "high" ? 3
                            : severity === "medium" ? 2
                            : severity === "low" ? 1
                            : 0,
                        ) }}>
                          {titleCase(severity)}
                        </span>
                      </td>
                      {visibleLanes.map((lane) => {
                        const hasIt = lane.audits.some((a) =>
                          a.report.findings.some((f) => findingKey(f.title, f.severity, f.category) === fKey),
                        );
                        return (
                          <td key={lane.serviceId} className="ma-table-check">
                            {hasIt ? (
                              <span className="ma-check-yes">✓</span>
                            ) : (
                              <span className="ma-check-no">—</span>
                            )}
                          </td>
                        );
                      })}
                      <td>
                        <span className={`ma-finding-agree-badge ${
                          isUniversal ? "ma-badge-agreed" : "ma-badge-partial"
                        }`}>
                          {agreeCount}/{totalAgents}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </div>
  );
}
