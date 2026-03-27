"use client";

import { useState } from "react";
import type { ChallengePolicy } from "../lib/types";
import {
  policyMatchesPreset,
  policyPresetLabel,
  policyOpennessLabel,
  policySummary,
  policySeverityLabel,
  policyEvidenceLabel,
  titleCase,
} from "../lib/format";

type PolicyBadgeProps = {
  policy: ChallengePolicy;
  admissibilityStatus?: string | null;
  admissibilityRationale?: string | null;
};

const OPENNESS_COLORS: Record<string, string> = {
  Open: "var(--secondary)",
  Balanced: "var(--tertiary)",
  Restrictive: "var(--error, #e53935)",
};

export function PolicyBadge({ policy, admissibilityStatus, admissibilityRationale }: PolicyBadgeProps) {
  const [expanded, setExpanded] = useState(false);
  const presetId = policyMatchesPreset(policy);
  const label = presetId ? `${policyPresetLabel(presetId)} Challenge Policy` : "Custom Challenge Policy";
  const summary = policySummary(policy);
  const opennessLabel = policyOpennessLabel(policy);
  const opennessColor = OPENNESS_COLORS[opennessLabel] ?? "var(--on-surface-variant)";

  return (
    <div className="card">
      <div className="card-body">
        <h3
          className="section-label"
          style={{ display: "flex", gap: 8, alignItems: "center" }}
        >
          <span>📋</span> CHALLENGE POLICY
        </h3>

        <div
          style={{
            marginTop: 14,
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <strong style={{ fontSize: "0.88rem" }}>{label}</strong>
          <span
            className="badge"
            style={{
              fontSize: "0.55rem",
              background: `${opennessColor}22`,
              color: opennessColor,
              border: `1px solid ${opennessColor}44`,
            }}
          >
            {opennessLabel}
          </span>
        </div>

        <p
          className="muted"
          style={{ fontSize: "0.72rem", lineHeight: 1.6, marginTop: 8 }}
        >
          {summary}
        </p>

        {admissibilityStatus ? (
          <div
            style={{
              marginTop: 12,
              padding: "10px 14px",
              borderRadius: 10,
              background:
                admissibilityStatus === "admissible"
                  ? "rgba(76,175,80,0.08)"
                  : "rgba(229,57,53,0.08)",
              border:
                admissibilityStatus === "admissible"
                  ? "1px solid rgba(76,175,80,0.25)"
                  : "1px solid rgba(229,57,53,0.25)",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span>
                {admissibilityStatus === "admissible" ? "✅" : "🚫"}
              </span>
              <strong style={{ fontSize: "0.78rem" }}>
                {admissibilityStatus === "admissible"
                  ? "Challenge Admissible"
                  : "Challenge Inadmissible"}
              </strong>
            </div>
            {admissibilityRationale ? (
              <p
                className="muted"
                style={{ fontSize: "0.68rem", lineHeight: 1.5, marginTop: 6 }}
              >
                {admissibilityRationale}
              </p>
            ) : null}
          </div>
        ) : null}

        <button
          type="button"
          onClick={() => setExpanded(!expanded)}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 6,
            marginTop: 12,
            background: "none",
            border: "none",
            cursor: "pointer",
            fontSize: "0.68rem",
            color: "var(--primary)",
            padding: 0,
          }}
        >
          <span
            style={{
              transform: expanded ? "rotate(90deg)" : "rotate(0deg)",
              transition: "transform 0.15s ease",
              display: "inline-block",
            }}
          >
            ›
          </span>
          {expanded ? "Hide details" : "Policy details"}
        </button>

        {expanded ? (
          <div
            style={{
              marginTop: 10,
              display: "grid",
              gap: 8,
            }}
          >
            <div
              style={{
                padding: "10px 14px",
                borderRadius: 8,
                background: "var(--surface-container-low)",
              }}
            >
              <div className="hash-label">SEVERITY THRESHOLD</div>
              <div style={{ fontSize: "0.78rem", marginTop: 4 }}>
                {policySeverityLabel(policy.min_severity_threshold)}
              </div>
            </div>
            <div
              style={{
                padding: "10px 14px",
                borderRadius: 8,
                background: "var(--surface-container-low)",
              }}
            >
              <div className="hash-label">EVIDENCE TYPES</div>
              <div style={{ fontSize: "0.78rem", marginTop: 4 }}>
                {policyEvidenceLabel(policy.allowed_evidence_types)}
              </div>
            </div>
            <div
              style={{
                padding: "10px 14px",
                borderRadius: 8,
                background: "var(--surface-container-low)",
              }}
            >
              <div className="hash-label">ADMISSIBILITY MODE</div>
              <div style={{ fontSize: "0.78rem", marginTop: 4 }}>
                {titleCase(policy.admissibility_mode)}
              </div>
            </div>
            <div
              style={{
                display: "flex",
                gap: 16,
              }}
            >
              <div
                style={{
                  flex: 1,
                  padding: "10px 14px",
                  borderRadius: 8,
                  background: "var(--surface-container-low)",
                }}
              >
                <div className="hash-label">INFORMATIONAL-ONLY</div>
                <div style={{ fontSize: "0.78rem", marginTop: 4 }}>
                  {policy.allow_informational_only ? "Allowed" : "Not allowed"}
                </div>
              </div>
              <div
                style={{
                  flex: 1,
                  padding: "10px 14px",
                  borderRadius: 8,
                  background: "var(--surface-container-low)",
                }}
              >
                <div className="hash-label">MATERIAL INCORRECTNESS</div>
                <div style={{ fontSize: "0.78rem", marginTop: 4 }}>
                  {policy.requires_material_incorrectness ? "Required" : "Not required"}
                </div>
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
