"use client";

import type { DemoFixture, InputKind, PublicContractConfig } from "../lib/types";

type SubmitPanelProps = {
  submissionMode: InputKind;
  contractAddress: string;
  selectedFixtureId: string;
  entryContract: string;
  sourceBundleUri: string;
  sourceBundleLabel: string;
  selectedFixture: DemoFixture | undefined;
  isPending: boolean;
  activeAction: string | null;
  config: PublicContractConfig | null;
  onModeChange: (mode: InputKind) => void;
  onContractAddressChange: (v: string) => void;
  onEntryContractChange: (v: string) => void;
  onSourceBundleUriChange: (v: string) => void;
  onSourceBundleLabelChange: (v: string) => void;
  onSubmit: () => void;
};

const MODES: { id: InputKind; label: string }[] = [
  { id: "demo_fixture",     label: "Demo fixture" },
  { id: "deployed_address", label: "Deployed address" },
  { id: "source_bundle",    label: "Source bundle" },
];

export function SubmitPanel({
  submissionMode,
  contractAddress,
  entryContract,
  sourceBundleUri,
  sourceBundleLabel,
  selectedFixture,
  isPending,
  activeAction,
  onModeChange,
  onContractAddressChange,
  onEntryContractChange,
  onSourceBundleUriChange,
  onSourceBundleLabelChange,
  onSubmit,
}: SubmitPanelProps) {
  return (
    <div className="card">
      <div className="card-body submit-panel">
        <h3 style={{ fontSize: "0.88rem", fontWeight: 700, display: "flex", alignItems: "center", gap: 8 }}>
          <span>📤</span>
          Artifact Submission
        </h3>

        {/* Mode tabs */}
        <div style={{ display: "flex", gap: 8 }}>
          {MODES.map((m) => (
            <button
              key={m.id}
              type="button"
              className="badge"
              style={{
                cursor: "pointer",
                padding: "6px 14px",
                background: submissionMode === m.id ? "var(--primary-container)" : "var(--surface-container-high)",
                color: submissionMode === m.id ? "var(--on-primary-container)" : "var(--on-surface-variant)",
                border: "1px solid rgba(67,70,85,0.2)",
              }}
              onClick={() => onModeChange(m.id)}
            >
              {m.label}
            </button>
          ))}
        </div>

        {submissionMode === "source_bundle" ? (
          <>
            <div className="drop-zone">
              <div className="icon">☁️</div>
              <p>Drop .zip or .sol files here</p>
            </div>
            <div className="or-divider"><span>Or</span></div>
            <div>
              <label className="section-label">Bundle URI</label>
              <input
                className="input-field mono"
                placeholder="ipfs://... or https://..."
                value={sourceBundleUri}
                onChange={(e) => onSourceBundleUriChange(e.target.value)}
              />
            </div>
            <div>
              <label className="section-label">Bundle label</label>
              <input
                className="input-field"
                placeholder="e.g. my-vault-v3"
                value={sourceBundleLabel}
                onChange={(e) => onSourceBundleLabelChange(e.target.value)}
              />
            </div>
          </>
        ) : (
          <>
            <div>
              <label className="section-label">Deployed Address</label>
              <input
                className="input-field mono"
                placeholder="0x..."
                value={contractAddress}
                onChange={(e) => onContractAddressChange(e.target.value)}
              />
            </div>
            <div>
              <label className="section-label">Entry Contract</label>
              <input
                className="input-field"
                value={entryContract}
                onChange={(e) => onEntryContractChange(e.target.value)}
              />
            </div>
            {selectedFixture ? (
              <p className="muted" style={{ fontSize: "0.78rem" }}>
                {selectedFixture.label} selected for a reproducible demo.
              </p>
            ) : null}
          </>
        )}

        <button
          type="button"
          className="cta-primary"
          disabled={isPending || !contractAddress}
          onClick={onSubmit}
          data-testid="submit-audit"
        >
          <span>🔬</span>
          {activeAction ?? "Run Security Analysis"}
        </button>
      </div>
    </div>
  );
}
