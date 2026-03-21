"use client";

import type {
  AuditorServiceRecord,
  DemoFixture,
  InputKind,
  PublicContractConfig,
} from "../lib/types";

type SubmitPanelProps = {
  submissionMode: InputKind;
  contractAddress: string;
  selectedFixtureId: string;
  auditorServices: AuditorServiceRecord[];
  selectedServiceId: string;
  selectedAuditorService: AuditorServiceRecord | null;
  entryContract: string;
  sourceBundleUri: string;
  sourceBundleLabel: string;
  selectedFixture: DemoFixture | undefined;
  isPending: boolean;
  activeAction: string | null;
  config: PublicContractConfig | null;
  onModeChange: (mode: InputKind) => void;
  onSelectedServiceIdChange: (serviceId: string) => void;
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
  selectedFixtureId,
  auditorServices,
  selectedServiceId,
  selectedAuditorService,
  entryContract,
  sourceBundleUri,
  sourceBundleLabel,
  selectedFixture,
  isPending,
  activeAction,
  config,
  onModeChange,
  onSelectedServiceIdChange,
  onContractAddressChange,
  onEntryContractChange,
  onSourceBundleUriChange,
  onSourceBundleLabelChange,
  onSubmit,
}: SubmitPanelProps) {
  const trimmedContractAddress = contractAddress.trim();
  const trimmedSourceBundleUri = sourceBundleUri.trim();
  const selectedServiceSupportsMode = selectedAuditorService
    ? selectedAuditorService.submission_modes.includes(submissionMode)
    : false;
  const canSubmit =
    !isPending &&
    selectedServiceSupportsMode &&
    (
      (submissionMode === "demo_fixture" && selectedFixtureId.trim().length > 0) ||
      (submissionMode === "deployed_address" && trimmedContractAddress.length > 0) ||
      (submissionMode === "source_bundle" && trimmedSourceBundleUri.length > 0)
    );

  return (
    <div className="card">
      <div className="card-body submit-panel">
        <h3 style={{ fontSize: "0.88rem", fontWeight: 700, display: "flex", alignItems: "center", gap: 8 }}>
          <span>📤</span>
          Artifact Submission
        </h3>

        <div>
          <label className="section-label">Auditor Service</label>
          <select
            className="input-field"
            value={selectedServiceId}
            onChange={(e) => onSelectedServiceIdChange(e.target.value)}
            disabled={isPending || auditorServices.length === 0}
            data-testid="auditor-service-select"
          >
            {auditorServices.map((service) => (
              <option key={service.service_id} value={service.service_id}>
                {service.name}
              </option>
            ))}
          </select>
          {selectedAuditorService ? (
            <p className="muted" style={{ fontSize: "0.78rem", marginTop: 8, lineHeight: 1.5 }}>
              {selectedAuditorService.capability} via {selectedAuditorService.execution_mode}
              {" · "}
              supports {selectedAuditorService.submission_modes.map((mode) => mode.replace("_", " ")).join(", ")}
            </p>
          ) : (
            <p className="muted" style={{ fontSize: "0.78rem", marginTop: 8 }}>
              No auditor services are currently available.
            </p>
          )}
          {selectedAuditorService && !selectedServiceSupportsMode ? (
            <p className="notice-banner notice-banner-info" style={{ marginTop: 8 }}>
              {selectedAuditorService.name} does not support {submissionMode.replace("_", " ")} submissions.
            </p>
          ) : null}
        </div>

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
                data-testid="source-bundle-uri"
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
            <div>
              <label className="section-label">Entry Contract</label>
              <input
                className="input-field"
                placeholder="Entry contract (optional)"
                value={entryContract}
                onChange={(e) => onEntryContractChange(e.target.value)}
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
          disabled={!canSubmit}
          onClick={onSubmit}
          data-testid="submit-audit"
        >
          <span>🔬</span>
          {activeAction ?? "Run Security Analysis"}
        </button>
        {config?.auditor_service?.service_id === selectedServiceId ? null : selectedAuditorService ? (
          <p className="muted" style={{ fontSize: "0.76rem", lineHeight: 1.5 }}>
            New claims will be stored under {selectedAuditorService.name} and compared separately from other auditors for the same target.
          </p>
        ) : null}
      </div>
    </div>
  );
}
