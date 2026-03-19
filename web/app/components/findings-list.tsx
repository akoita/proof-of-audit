"use client";

import { useState } from "react";
import type { Finding } from "../lib/types";
import { titleCase } from "../lib/format";

type FindingsListProps = { findings: Finding[] };

const SEVERITY_COLORS: Record<string, { bg: string; border: string; text: string; dot: string }> = {
  critical: { bg: "rgba(234,67,53,0.08)", border: "rgba(234,67,53,0.25)", text: "var(--error)", dot: "#EA4335" },
  high:     { bg: "rgba(251,188,4,0.08)",  border: "rgba(251,188,4,0.25)",  text: "var(--tertiary)", dot: "#FBBC04" },
  medium:   { bg: "rgba(66,133,244,0.08)", border: "rgba(66,133,244,0.20)", text: "var(--primary)", dot: "#4285F4" },
  low:      { bg: "rgba(52,168,83,0.06)",  border: "rgba(52,168,83,0.15)",  text: "var(--secondary)", dot: "#34A853" },
  info:     { bg: "var(--surface-container-high)", border: "var(--outline-variant)", text: "var(--on-surface-variant)", dot: "var(--on-surface-variant)" },
};

function severityStyle(severity: string) {
  return SEVERITY_COLORS[severity.toLowerCase()] ?? SEVERITY_COLORS.info;
}

export function FindingsList({ findings }: FindingsListProps) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  return (
    <div className="card">
      <div className="card-body">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <h3 style={{ fontSize: "0.95rem", fontWeight: 700, display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: "1.1rem" }}>🔬</span>
            Findings
          </h3>
          <span style={{
            background: findings.length > 0 ? "rgba(234,67,53,0.15)" : "var(--secondary-container)",
            color: findings.length > 0 ? "var(--error)" : "white",
            borderRadius: 20,
            padding: "3px 10px",
            fontSize: "0.6rem",
            fontWeight: 700,
          }}>
            {findings.length}
          </span>
        </div>

        {findings.length === 0 ? (
          <div style={{
            marginTop: 14,
            padding: "16px 18px",
            borderRadius: 10,
            background: "rgba(52,168,83,0.06)",
            border: "1px solid rgba(52,168,83,0.15)",
            display: "flex",
            alignItems: "center",
            gap: 10,
          }}>
            <span style={{ fontSize: "1.2rem" }}>✅</span>
            <div>
              <strong style={{ fontSize: "0.82rem" }}>No benchmark issue found</strong>
              <p className="muted" style={{ fontSize: "0.72rem", marginTop: 2 }}>
                The auditor did not match a benchmark issue across the supported checks.
              </p>
            </div>
          </div>
        ) : (
          <div style={{ display: "grid", gap: 10, marginTop: 14 }}>
            {findings.map((finding) => {
              const s = severityStyle(finding.severity);
              const isOpen = expandedId === finding.finding_id;

              return (
                <button
                  key={finding.finding_id}
                  type="button"
                  onClick={() => setExpandedId(isOpen ? null : finding.finding_id)}
                  style={{
                    background: s.bg,
                    border: `1px solid ${s.border}`,
                    borderRadius: 10,
                    padding: "14px 16px",
                    cursor: "pointer",
                    textAlign: "left",
                    color: "var(--on-surface)",
                    transition: "all 0.15s",
                    width: "100%",
                  }}
                >
                  {/* Header row */}
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0, flex: 1 }}>
                      <span style={{
                        width: 8,
                        height: 8,
                        borderRadius: "50%",
                        background: s.dot,
                        flexShrink: 0,
                      }} />
                      <span style={{
                        fontWeight: 600,
                        fontSize: "0.82rem",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}>
                        {finding.title}
                      </span>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0, marginLeft: 12 }}>
                      <span style={{
                        fontSize: "0.55rem",
                        fontWeight: 700,
                        textTransform: "uppercase",
                        color: s.text,
                        padding: "2px 8px",
                        borderRadius: 6,
                        background: `${s.dot}22`,
                      }}>
                        {finding.severity}
                      </span>
                      <span style={{
                        fontSize: "0.7rem",
                        color: "var(--on-surface-variant)",
                        transition: "transform 0.15s",
                        transform: isOpen ? "rotate(180deg)" : "rotate(0deg)",
                      }}>
                        ▾
                      </span>
                    </div>
                  </div>

                  {/* Subtitle */}
                  <div className="muted" style={{ fontSize: "0.68rem", marginTop: 6, marginLeft: 18 }}>
                    {titleCase(finding.category)} · {titleCase(finding.confidence)} confidence
                    {finding.affected_function ? (
                      <span> · <code className="mono" style={{ fontSize: "0.65rem", color: "var(--primary)" }}>{finding.affected_function}</code></span>
                    ) : null}
                  </div>

                  {/* Expandable details */}
                  {isOpen ? (
                    <div style={{ marginTop: 12, marginLeft: 18, display: "grid", gap: 8 }}>
                      {/* Description */}
                      <p style={{ fontSize: "0.78rem", lineHeight: 1.6 }}>
                        {finding.description}
                      </p>

                      {/* Impact */}
                      {finding.impact ? (
                        <div style={{
                          padding: "10px 14px",
                          borderRadius: 8,
                          background: "var(--surface-container-high)",
                        }}>
                          <div className="hash-label" style={{ marginBottom: 4 }}>IMPACT</div>
                          <p style={{ fontSize: "0.72rem", lineHeight: 1.5, color: "var(--on-surface)" }}>
                            {finding.impact}
                          </p>
                        </div>
                      ) : null}

                      {/* Recommendation */}
                      {finding.recommendation ? (
                        <div style={{
                          padding: "10px 14px",
                          borderRadius: 8,
                          background: "var(--surface-container-high)",
                        }}>
                          <div className="hash-label" style={{ marginBottom: 4 }}>RECOMMENDATION</div>
                          <p style={{ fontSize: "0.72rem", lineHeight: 1.5, color: "var(--on-surface)" }}>
                            {finding.recommendation}
                          </p>
                        </div>
                      ) : null}

                      {/* Source + Evidence row */}
                      <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                        {finding.source_path ? (
                          <div className="hash-card" style={{ padding: "8px 12px", flex: 1 }}>
                            <div className="hash-label">SOURCE</div>
                            <code className="mono" style={{ fontSize: "0.65rem" }}>
                              {finding.source_path}
                              {finding.start_line ? `:${finding.start_line}` : ""}
                              {finding.end_line && finding.end_line !== finding.start_line ? `-${finding.end_line}` : ""}
                            </code>
                          </div>
                        ) : null}
                        {finding.evidence_uri ? (
                          <div className="hash-card" style={{ padding: "8px 12px", flex: 1 }}>
                            <div className="hash-label">EVIDENCE</div>
                            <a
                              href={finding.evidence_uri}
                              target="_blank"
                              rel="noreferrer"
                              onClick={(e) => e.stopPropagation()}
                              style={{ fontSize: "0.65rem", color: "var(--primary)" }}
                            >
                              {finding.evidence_uri}
                            </a>
                          </div>
                        ) : null}
                      </div>
                    </div>
                  ) : null}
                </button>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
