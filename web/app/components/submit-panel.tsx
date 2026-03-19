"use client";

import type { FormEvent } from "react";
import type { DemoFixture, InputKind, PublicContractConfig } from "../lib/types";

type SubmitPanelProps = {
  submissionMode: InputKind;
  contractAddress: string;
  selectedFixtureId: string;
  entryContract: string;
  sourceBundleUri: string;
  sourceBundleLabel: string;
  selectedFixture: DemoFixture | null;
  isPending: boolean;
  activeAction: string | null;
  config: PublicContractConfig | null;
  onModeChange: (mode: InputKind) => void;
  onContractAddressChange: (value: string) => void;
  onEntryContractChange: (value: string) => void;
  onSourceBundleUriChange: (value: string) => void;
  onSourceBundleLabelChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
};

const MODES: { mode: InputKind; label: string }[] = [
  { mode: "demo_fixture", label: "Demo fixture" },
  { mode: "deployed_address", label: "Deployed address" },
  { mode: "source_bundle", label: "Source bundle" },
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
    <form className="submit-card" onSubmit={onSubmit}>
      <div className="submit-card-heading">
        <div>
          <label htmlFor="contractAddress">Audit target</label>
          <p>
            Choose how the target code is provided, then generate an audit claim.
          </p>
        </div>
        {selectedFixture ? (
          <span className="fixture-pill">{selectedFixture.label}</span>
        ) : null}
      </div>

      <div className="mode-switch" role="tablist" aria-label="Audit input mode">
        {MODES.map(({ mode, label }) => (
          <button
            key={mode}
            className="mode-chip"
            data-selected={submissionMode === mode}
            type="button"
            onClick={() => onModeChange(mode)}
          >
            {label}
          </button>
        ))}
      </div>

      {submissionMode === "source_bundle" ? (
        <div className="submission-fields">
          <input
            id="sourceBundleUri"
            placeholder="ipfs://uploads/dual-risk-vault.zip"
            value={sourceBundleUri}
            onChange={(e) => onSourceBundleUriChange(e.target.value)}
          />
          <input
            id="entryContract"
            placeholder="Entry contract (optional)"
            value={entryContract}
            onChange={(e) => onEntryContractChange(e.target.value)}
          />
          <input
            id="sourceBundleLabel"
            placeholder="Bundle label (optional)"
            value={sourceBundleLabel}
            onChange={(e) => onSourceBundleLabelChange(e.target.value)}
          />
        </div>
      ) : (
        <div className="submission-fields">
          <input
            id="contractAddress"
            placeholder="0x..."
            value={contractAddress}
            onChange={(e) => onContractAddressChange(e.target.value)}
            disabled={submissionMode === "demo_fixture"}
          />
          <input
            id="entryContract"
            placeholder="Entry contract (optional)"
            value={entryContract}
            onChange={(e) => onEntryContractChange(e.target.value)}
          />
        </div>
      )}

      <div className="submit-card-footer">
        <p className="helper-copy">
          {submissionMode === "demo_fixture"
            ? selectedFixture
              ? `${selectedFixture.contract_name} selected for a reproducible demo.`
              : "Pick a demo fixture below to populate the address."
            : submissionMode === "source_bundle"
              ? "Provide a bundle URI for source-level audit."
              : "Paste a deployed contract address."}
        </p>
        <button type="submit" disabled={isPending}>
          {isPending && activeAction?.includes("Generating")
            ? "Working…"
            : "Generate claim"}
        </button>
      </div>
    </form>
  );
}
