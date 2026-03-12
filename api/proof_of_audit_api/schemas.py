from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class FindingModel(BaseModel):
    title: str
    severity: str
    description: str
    recommendation: str
    detector: str


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


class OnchainPublicationModel(BaseModel):
    network: str
    chain_id: int
    contract_address: str | None = None
    explorer_base_url: str
    agent_identity: str
    stake_wei: int
    report_hash: str
    metadata_hash: str
    max_severity: int
    finding_count: int
    publish_tx_hash: str
    publish_tx_url: str | None = None


class ChallengeModel(BaseModel):
    challenger: str
    proof_uri: str
    submitted_at: str
    verifier: str
    status: str
    challenge_tx_hash: str
    challenge_tx_url: str | None = None


class AuditRecordModel(BaseModel):
    id: str
    contract_address: str
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
    required_stake_wei: int
    required_challenge_bond_wei: int
    challenge_window_seconds: int
    deployment_ready: bool


class CreateAuditRequest(BaseModel):
    contract_address: str
    submitted_by: str = "anonymous"


class PublishAuditRequest(BaseModel):
    stake_wei: int = Field(default=10_000_000_000_000_000, ge=0)
    agent_identity: str = "auditor-agent-v1"


class ChallengeAuditRequest(BaseModel):
    proof_uri: str
    challenger: str = "anonymous-challenger"


class ErrorResponse(BaseModel):
    error: str
    message: str | None = None
    field: str | None = None
    detail: Any | None = None
