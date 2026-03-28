"use client";

import { ChangeEvent, DragEvent, useRef, useState } from "react";

import type {
  AuditorServiceRecord,
  DemoFixture,
  InputKind,
  PublicContractConfig,
} from "../lib/types";

type SubmitPanelProps = {
  submissionMode: InputKind;
  allowDemoFixtures: boolean;
  contractAddress: string;
  selectedFixtureId: string;
  auditorServices: AuditorServiceRecord[];
  selectedServiceId: string;
  selectedAuditorService: AuditorServiceRecord | null;
  entryContract: string;
  sourceBundleUri: string;
  sourceBundleLabel: string;
  selectedFixture: DemoFixture | undefined;
  isLoaded: boolean;
  loadError: string | null;
  isPending: boolean;
  activeAction: string | null;
  config: PublicContractConfig | null;
  onModeChange: (mode: InputKind) => void;
  onSelectedServiceIdChange: (serviceId: string) => void;
  onContractAddressChange: (v: string) => void;
  onEntryContractChange: (v: string) => void;
  onSourceBundleUriChange: (v: string) => void;
  onSourceBundleLabelChange: (v: string) => void;
  onSourceBundleFileSelect: (file: File) => void;
  isUploadingSourceBundle: boolean;
  onSubmit: () => void;
};

const MODES: { id: InputKind; label: string }[] = [
  { id: "demo_fixture",     label: "Demo fixture" },
  { id: "deployed_address", label: "Deployed address" },
  { id: "source_bundle",    label: "Source bundle" },
];

function publicationModeSummary(
  publicationMode: string | null | undefined,
  serviceName: string,
): string | null {
  if (publicationMode === "api_mediated") {
    return `${serviceName} stakes and submits the on-chain publish transaction. Your connected wallet is not charged for publish in this mode.`;
  }
  if (publicationMode === "self_published") {
    return `Your connected wallet must sign and fund the publish transaction for ${serviceName}.`;
  }
  return null;
}

export function SubmitPanel({
  submissionMode,
  allowDemoFixtures,
  contractAddress,
  selectedFixtureId,
  auditorServices,
  selectedServiceId,
  selectedAuditorService,
  entryContract,
  sourceBundleUri,
  sourceBundleLabel,
  selectedFixture,
  isLoaded,
  loadError,
  isPending,
  activeAction,
  config,
  onModeChange,
  onSelectedServiceIdChange,
  onContractAddressChange,
  onEntryContractChange,
  onSourceBundleUriChange,
  onSourceBundleLabelChange,
  onSourceBundleFileSelect,
  isUploadingSourceBundle,
  onSubmit,
}: SubmitPanelProps) {
  const [isDragActive, setIsDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const availableModes = allowDemoFixtures
    ? MODES
    : MODES.filter((mode) => mode.id !== "demo_fixture");
  const trimmedContractAddress = contractAddress.trim();
  const trimmedSourceBundleUri = sourceBundleUri.trim();
  const selectedServiceSupportsMode = selectedAuditorService
    ? selectedAuditorService.submission_modes.includes(submissionMode)
    : false;
  const publicationSummary = selectedAuditorService
    ? publicationModeSummary(
        selectedAuditorService.publication_mode,
        selectedAuditorService.name,
      )
    : null;
  const auditorServiceStatusMessage = !isLoaded
    ? "Loading auditor services..."
    : loadError
      ? "Auditor services could not be loaded."
      : "No auditor services are currently available.";
  const canSubmit =
    !isPending &&
    selectedServiceSupportsMode &&
    (
      (submissionMode === "demo_fixture" && selectedFixtureId.trim().length > 0) ||
      (submissionMode === "deployed_address" && trimmedContractAddress.length > 0) ||
      (submissionMode === "source_bundle" && trimmedSourceBundleUri.length > 0)
    );
  const selectedBundleName =
    sourceBundleLabel.trim() ||
    trimmedSourceBundleUri.split(/[\\/]/).pop() ||
    "";

  function handleFileList(fileList: FileList | null) {
    const file = fileList?.[0];
    if (!file || isPending) return;
    onSourceBundleFileSelect(file);
  }

  function handleFileInputChange(event: ChangeEvent<HTMLInputElement>) {
    handleFileList(event.target.files);
    event.target.value = "";
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    event.stopPropagation();
    setIsDragActive(false);
    handleFileList(event.dataTransfer.files);
  }

  function handleDragOver(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    event.stopPropagation();
    event.dataTransfer.dropEffect = "copy";
    if (!isPending) {
      setIsDragActive(true);
    }
  }

  function handleDragLeave(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    event.stopPropagation();
    setIsDragActive(false);
  }

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
            disabled={isPending || !isLoaded || auditorServices.length === 0}
            data-testid="auditor-service-select"
          >
            {auditorServices.map((service) => (
              <option key={service.service_id} value={service.service_id}>
                {service.name}
              </option>
            ))}
          </select>
          {selectedAuditorService ? (
            <>
              <p className="muted" style={{ fontSize: "0.78rem", marginTop: 8, lineHeight: 1.5 }}>
                {selectedAuditorService.capability} via {selectedAuditorService.execution_mode}
                {" · "}
                supports {selectedAuditorService.submission_modes.map((mode) => mode.replace("_", " ")).join(", ")}
              </p>
              {publicationSummary ? (
                <p className="notice-banner notice-banner-info" style={{ marginTop: 8 }}>
                  {publicationSummary}
                </p>
              ) : null}
            </>
          ) : (
            <p className="muted" style={{ fontSize: "0.78rem", marginTop: 8 }}>
              {auditorServiceStatusMessage}
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
          {availableModes.map((m) => (
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
              data-testid={`submission-mode-${m.id}`}
            >
              {m.label}
            </button>
          ))}
        </div>

        {submissionMode === "source_bundle" ? (
          <>
            <input
              ref={fileInputRef}
              type="file"
              accept=".zip,.sol"
              hidden
              onChange={handleFileInputChange}
              data-testid="source-bundle-file-input"
            />
            <div
              className={`drop-zone${isDragActive ? " drag-active" : ""}${isPending ? " is-disabled" : ""}`}
              role="button"
              tabIndex={isPending ? -1 : 0}
              onClick={() => {
                if (!isPending) {
                  fileInputRef.current?.click();
                }
              }}
              onKeyDown={(event) => {
                if (isPending) return;
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  fileInputRef.current?.click();
                }
              }}
              onDrop={handleDrop}
              onDragEnter={handleDragOver}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              data-testid="source-bundle-drop-zone"
            >
              <div className="icon">☁️</div>
              <p>{isUploadingSourceBundle ? "Uploading source bundle..." : "Drop .zip or .sol files here"}</p>
              <p className="drop-zone-detail">
                {selectedBundleName || "Stored via the API's configured local, GCS, or IPFS backend"}
              </p>
              <button
                type="button"
                className="cta-secondary file-picker-button"
                disabled={isPending}
                onClick={(event) => {
                  event.stopPropagation();
                  fileInputRef.current?.click();
                }}
                data-testid="source-bundle-choose-file"
              >
                Choose File or ZIP
              </button>
            </div>
            <div className="or-divider"><span>Or</span></div>
            <div>
              <label className="section-label">Bundle URI</label>
              <input
                className="input-field mono"
                placeholder="ipfs://..., gs://..., https://..., or local file path"
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
            {submissionMode === "demo_fixture" && selectedFixture ? (
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
