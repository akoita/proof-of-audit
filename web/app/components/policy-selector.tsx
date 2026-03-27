"use client";

import type { ChallengePolicy, ChallengePolicyPresetId } from "../lib/types";
import { POLICY_PRESETS, policyOpennessLabel } from "../lib/format";

type PolicySelectorProps = {
  selectedPresetId: ChallengePolicyPresetId;
  onSelect: (presetId: ChallengePolicyPresetId, policy: ChallengePolicy) => void;
};

const OPENNESS_COLORS: Record<string, string> = {
  Open: "var(--secondary)",
  Balanced: "var(--tertiary)",
  Restrictive: "var(--error, #e53935)",
};

export function PolicySelector({ selectedPresetId, onSelect }: PolicySelectorProps) {
  const presets = Object.values(POLICY_PRESETS);

  return (
    <div className="policy-selector" style={{ marginTop: 14 }}>
      <div
        className="hash-label"
        style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 10 }}
      >
        <span>📋</span> CHALLENGE POLICY
      </div>
      <p className="muted" style={{ fontSize: "0.7rem", lineHeight: 1.5, marginBottom: 12 }}>
        Choose how open this claim is to challenges. This policy is immutable once published and
        affects your reputation openness score.
      </p>
      <div style={{ display: "grid", gap: 10 }}>
        {presets.map((preset) => {
          const isActive = preset.id === selectedPresetId;
          const opennessLabel = policyOpennessLabel(preset.policy);
          const opennessColor = OPENNESS_COLORS[opennessLabel] ?? "var(--on-surface-variant)";
          return (
            <button
              key={preset.id}
              type="button"
              onClick={() => onSelect(preset.id, preset.policy)}
              data-testid={`policy-preset-${preset.id}`}
              style={{
                display: "grid",
                gap: 6,
                padding: "14px 16px",
                borderRadius: 12,
                border: isActive
                  ? "2px solid var(--primary)"
                  : "1.5px solid rgba(67,70,85,0.2)",
                background: isActive
                  ? "rgba(187,134,252,0.06)"
                  : "var(--surface-container-low)",
                cursor: "pointer",
                textAlign: "left",
                transition: "all 0.15s ease",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span
                    style={{
                      width: 16,
                      height: 16,
                      borderRadius: "50%",
                      border: isActive
                        ? "5px solid var(--primary)"
                        : "2px solid var(--on-surface-variant)",
                      background: isActive ? "var(--surface)" : "transparent",
                      transition: "all 0.15s ease",
                    }}
                  />
                  <strong style={{ fontSize: "0.82rem" }}>{preset.label}</strong>
                </div>
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
                style={{ fontSize: "0.68rem", lineHeight: 1.5, margin: 0, paddingLeft: 24 }}
              >
                {preset.description}
              </p>
            </button>
          );
        })}
      </div>
    </div>
  );
}
