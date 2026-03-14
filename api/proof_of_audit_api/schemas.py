from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class AuditorProfileModel(BaseModel):
    id: str
    name: str
    version: str
    manifest_schema: str
    service_type: str
    description: str
    capabilities: list[str]
    operator: str
    resolution_policy: str


class AuditorServiceRecordModel(BaseModel):
    service_id: str
    name: str
    manifest_schema: str
    manifest_hash: str
    registration_kind: str
    capability: str
    discovery_path: str
    submit_path: str
    publish_path_template: str
    challenge_path_template: str
    network: str
    registry_contract_address: str | None = None


class FindingModel(BaseModel):
    finding_id: str
    title: str
    severity: str
    category: str
    description: str
    impact: str
    recommendation: str
    detector: str
    confidence: str
    affected_function: str | None = None
    source_path: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    evidence_uri: str | None = None


class AuditReportModel(BaseModel):
    benchmark_id: str
    contract_address: str
    summary: str
    findings: list[FindingModel]
    supported_checks: list[str]
    confidence: str
    report_hash: str
    metadata_hash: str
    max_severity: int
    finding_count: int
    severity_breakdown: dict[str, int]


class OnchainPublicationModel(BaseModel):
    audit_id: int | None = None
    network: str
    chain_id: int
    contract_address: str | None = None
    explorer_base_url: str
    agent_identity: str
    agent_name: str | None = None
    agent_version: str | None = None
    stake_wei: int
    report_hash: str
    metadata_hash: str
    max_severity: int
    finding_count: int
    publish_tx_hash: str
    publish_tx_url: str | None = None


class ChallengeModel(BaseModel):
    challenger: str
    challenger_address: str | None = None
    proof_uri: str
    submitted_at: str
    verifier: str
    status: str
    verification_status: str | None = None
    verification_summary: str | None = None
    verification_detail: str | None = None
    verification_case_id: str | None = None
    resolution: str | None = None
    resolved_at: str | None = None
    resolved_by: str | None = None
    beneficiary_address: str | None = None
    payout_wei: int | None = None
    challenge_hash: str | None = None
    challenge_bond_wei: int | None = None
    chain_id: int | None = None
    challenge_tx_hash: str
    challenge_tx_url: str | None = None
    resolve_tx_hash: str | None = None
    resolve_tx_url: str | None = None


class AuditRecordModel(BaseModel):
    id: str
    contract_address: str
    agent: AuditorProfileModel
    submission: "AuditSubmissionModel"
    submitted_by: str
    status: str
    created_at: str
    report: AuditReportModel
    onchain: OnchainPublicationModel | None = None
    challenge: ChallengeModel | None = None


class AuditListResponse(BaseModel):
    items: list[AuditRecordModel]


class DemoFixtureModel(BaseModel):
    id: str
    label: str
    contract_name: str
    entry_contract: str
    benchmark_id: str
    address: str
    challenge_proof_uri: str
    note: str
    source_path: str


class DemoFixtureListResponse(BaseModel):
    items: list[DemoFixtureModel]


class HealthResponse(BaseModel):
    status: str


class PublicContractConfigResponse(BaseModel):
    network: str
    chain_id: int
    contract_address: str | None = None
    explorer_base_url: str
    arbiter: str | None = None
    auditor: AuditorProfileModel
    auditor_service: AuditorServiceRecordModel
    required_stake_wei: int
    required_challenge_bond_wei: int
    challenge_window_seconds: int
    deployment_ready: bool


InputKind = Literal["deployed_address", "demo_fixture", "source_bundle", "repository_url"]


class AuditSubmissionModel(BaseModel):
    input_kind: InputKind
    chain_id: int | None = None
    contract_address: str | None = None
    fixture_id: str | None = None
    entry_contract: str | None = None
    source_bundle_uri: str | None = None
    source_bundle_label: str | None = None
    repository_url: str | None = None


class CreateAuditRequest(AuditSubmissionModel):
    input_kind: InputKind = "deployed_address"
    submitted_by: str = "anonymous"

    @model_validator(mode="after")
    def validate_submission_requirements(self) -> "CreateAuditRequest":
        if self.input_kind == "deployed_address" and not self.contract_address:
            raise ValueError("contract_address is required for deployed_address submissions")
        if self.input_kind == "demo_fixture" and not self.fixture_id:
            raise ValueError("fixture_id is required for demo_fixture submissions")
        if self.input_kind == "source_bundle" and not self.source_bundle_uri:
            raise ValueError("source_bundle_uri is required for source_bundle submissions")
        if self.input_kind == "repository_url" and not self.repository_url:
            raise ValueError("repository_url is required for repository_url submissions")
        return self


class PublishAuditRequest(BaseModel):
    stake_wei: int = Field(default=10_000_000_000_000_000, ge=0)
    agent_identity: str | None = None


class ChallengeAuditRequest(BaseModel):
    proof_uri: str
    challenger: str = "anonymous-challenger"


class ResolveAuditRequest(BaseModel):
    upheld: bool
    resolved_by: str = "arbiter"


class ErrorResponse(BaseModel):
    error: str
    message: str | None = None
    field: str | None = None
    detail: Any | None = None
