from __future__ import annotations

from copy import deepcopy
from datetime import datetime, UTC
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any
from uuid import uuid4

from proof_of_audit_api.config import ContractConfig
from proof_of_audit_api.publisher import (
    OnchainConfigurationError,
    OnchainPublishError,
    OnchainResolveError,
    ProofOfAuditPublisher,
)
from proof_of_audit_api.validation_bridge import (
    ValidationBridgeError,
    ValidationRegistryBridge,
)
from proof_of_audit_agent.challenge_verifier import DeterministicChallengeVerifier
from proof_of_audit_agent.runtime import WorkerRuntimeConfig
from proof_of_audit_agent.worker import AuditWorker
from proof_of_audit_api.store import AuditStore, create_store


class AuditService:
    def __init__(
        self,
        data_root: Path,
        contract_config: ContractConfig | None = None,
        publisher: ProofOfAuditPublisher | None = None,
        arbiter_client: ProofOfAuditPublisher | None = None,
        validation_bridge: ValidationRegistryBridge | None = None,
        store: AuditStore | None = None,
        store_kind: str = "sqlite",
        store_path: Path | None = None,
    ) -> None:
        self.store = store or create_store(
            root=data_root,
            kind=store_kind,
            database_path=store_path,
        )
        self.contract_config = contract_config or ContractConfig.from_env()
        self.worker = AuditWorker(
            self.contract_config.demo_fixtures_file,
            runtime=WorkerRuntimeConfig.from_values(
                mode=self.contract_config.worker_runtime_mode,
                agent_forge_command=self.contract_config.agent_forge_command,
                agent_forge_provider=self.contract_config.agent_forge_provider,
                agent_forge_model=self.contract_config.agent_forge_model,
                agent_forge_max_iterations=self.contract_config.agent_forge_max_iterations,
                agent_forge_runs_home=self.contract_config.agent_forge_runs_home,
            ),
            workspace_root=data_root,
        )
        self.challenge_verifier = DeterministicChallengeVerifier()
        self.publisher = publisher or ProofOfAuditPublisher.from_config_if_ready(
            self.contract_config
        )
        self.arbiter_client = arbiter_client or ProofOfAuditPublisher.from_config_if_ready(
            self.contract_config,
            private_key=self.contract_config.arbiter_private_key,
        )
        self.validation_bridge = validation_bridge or ValidationRegistryBridge.from_config_if_ready(
            self.contract_config
        )

    def create_audit(
        self, contract_address: str, submitted_by: str = "anonymous"
    ) -> dict[str, Any]:
        return self.create_audit_submission(
            {
                "input_kind": "deployed_address",
                "contract_address": contract_address,
            },
            submitted_by=submitted_by,
        )

    def create_audit_submission(
        self, submission: dict[str, Any], submitted_by: str = "anonymous"
    ) -> dict[str, Any]:
        normalized_submission = self._normalize_submission(submission)
        audit_id = str(uuid4())
        execution_result = self.worker.run_submission(
            audit_id=audit_id,
            **normalized_submission,
        )
        auditor = self.contract_config.auditor.to_dict()
        record = {
            "id": audit_id,
            "agent": auditor,
            "contract_address": normalized_submission["contract_address"],
            "submission": normalized_submission,
            "submitted_by": submitted_by,
            "status": "draft",
            "created_at": datetime.now(UTC).isoformat(),
            "report": execution_result.report.to_dict(),
            "execution": (
                execution_result.execution.to_dict()
                if execution_result.execution is not None
                else None
            ),
            "onchain": None,
            "challenge": None,
            "validation": None,
        }
        self.store.write(audit_id, record)
        return record

    def get_audit(self, audit_id: str) -> dict[str, Any] | None:
        record = self.store.read(audit_id)
        if record is None:
            return None
        return self._normalize_stored_record(record)

    def list_audits(self) -> list[dict[str, Any]]:
        records = [self._normalize_stored_record(record) for record in self.store.list_all()]
        return sorted(records, key=lambda record: record["created_at"], reverse=True)

    def list_demo_fixtures(self) -> list[dict[str, Any]]:
        return self.worker.list_demo_fixtures()

    def publish_audit(
        self, audit_id: str, stake_wei: int, agent_identity: str | None
    ) -> dict[str, Any]:
        record = self._require_audit(audit_id)
        if record["status"] != "draft":
            raise ValueError("audit must be in draft status before publish")
        if record["submission"]["input_kind"] == "source_bundle":
            raise ValueError("source_bundle submissions must be deployed before publish")
        if record["submission"]["input_kind"] == "repository_url":
            raise ValueError("repository_url submissions are not supported yet")
        if self.publisher is None:
            raise OnchainConfigurationError(
                "On-chain publishing is not configured for this API instance."
            )
        agent_identity = agent_identity or self.contract_config.auditor.id
        report = record["report"]
        publish_result = self.publisher.publish_audit(
            target_address=record["contract_address"],
            report_hash=report["report_hash"],
            metadata_hash=report["metadata_hash"],
            max_severity=report["max_severity"],
            finding_count=len(report["findings"]),
            stake_wei=stake_wei,
        )
        record["status"] = "published"
        record["onchain"] = {
            "audit_id": publish_result.audit_id,
            "network": self.contract_config.network,
            "chain_id": publish_result.chain_id,
            "contract_address": self.contract_config.contract_address,
            "explorer_base_url": self.contract_config.explorer_base_url,
            "agent_identity": agent_identity,
            "agent_name": self.contract_config.auditor.name,
            "agent_version": self.contract_config.auditor.version,
            "stake_wei": stake_wei,
            "report_hash": report["report_hash"],
            "metadata_hash": report["metadata_hash"],
            "max_severity": report["max_severity"],
            "finding_count": len(report["findings"]),
            "publish_tx_hash": publish_result.tx_hash,
            "publish_tx_url": self.contract_config.transaction_url(
                publish_result.tx_hash
            ),
        }
        record["validation"] = self._submit_validation_request(record)
        self.store.write(audit_id, record)
        return record

    def challenge_audit(
        self, audit_id: str, proof_uri: str, challenger: str
    ) -> dict[str, Any]:
        record = self._require_audit(audit_id)
        if record["challenge"] is not None or record["status"] in {"challenged", "resolved"}:
            raise ValueError("audit has already been challenged")
        if record["status"] != "published" or record["onchain"] is None:
            raise ValueError("audit must be published before challenge")
        onchain_audit_id = record["onchain"].get("audit_id")
        if not isinstance(onchain_audit_id, int):
            raise ValueError("published audit is missing its on-chain audit id")
        if self.publisher is None:
            raise OnchainConfigurationError(
                "On-chain challenge submission is not configured for this API instance."
            )

        challenge_result = self.publisher.challenge_audit(
            audit_id=onchain_audit_id,
            proof_uri=proof_uri,
            challenge_bond_wei=self.contract_config.required_challenge_bond_wei,
        )
        verification_result = self.challenge_verifier.verify(
            record["report"]["benchmark_id"],
            proof_uri,
        )
        challenge_record = {
            "challenger": challenger,
            "challenger_address": challenge_result.challenger_address,
            "proof_uri": proof_uri,
            "submitted_at": datetime.now(UTC).isoformat(),
            "verifier": verification_result.verifier,
            "status": "opened",
            "resolution_path": "manual_fallback",
            "verification_status": verification_result.status,
            "verification_summary": verification_result.summary,
            "verification_detail": verification_result.detail,
            "verification_case_id": verification_result.case_id,
            "challenge_hash": challenge_result.challenge_hash,
            "challenge_bond_wei": challenge_result.challenge_bond_wei,
            "chain_id": challenge_result.chain_id,
            "challenge_tx_hash": challenge_result.tx_hash,
            "challenge_tx_url": self.contract_config.transaction_url(
                challenge_result.tx_hash
            ),
        }

        if (
            verification_result.status == "verified"
            and verification_result.upheld is not None
            and self.arbiter_client is not None
        ):
            try:
                resolution_result = self.arbiter_client.resolve_challenge(
                    audit_id=onchain_audit_id,
                    upheld=verification_result.upheld,
                )
            except OnchainResolveError as exc:
                challenge_record["verification_detail"] = (
                    f"{verification_result.detail} Automatic on-chain resolution failed: {exc}"
                )
                record["status"] = "challenged"
            else:
                challenge_record.update(
                    {
                        "status": resolution_result.resolution,
                        "resolution_path": "deterministic",
                        "resolution": resolution_result.resolution,
                        "resolved_at": datetime.now(UTC).isoformat(),
                        "resolved_by": "deterministic-verifier",
                        "beneficiary_address": resolution_result.beneficiary_address,
                        "payout_wei": resolution_result.payout_wei,
                        "resolve_tx_hash": resolution_result.tx_hash,
                        "resolve_tx_url": self.contract_config.transaction_url(
                            resolution_result.tx_hash
                        ),
                    }
                )
                record["status"] = "resolved"
        else:
            record["status"] = "challenged"

        record["challenge"] = challenge_record
        if record["status"] == "resolved":
            record["validation"] = self._submit_validation_response(record)
        self.store.write(audit_id, record)
        return record

    def resolve_audit(
        self, audit_id: str, upheld: bool, resolved_by: str
    ) -> dict[str, Any]:
        record = self._require_audit(audit_id)
        if record["status"] != "challenged" or record["challenge"] is None:
            raise ValueError("audit must be challenged before resolution")
        onchain_audit_id = record.get("onchain", {}).get("audit_id")
        if not isinstance(onchain_audit_id, int):
            raise ValueError("challenged audit is missing its on-chain audit id")
        if self.arbiter_client is None:
            raise OnchainConfigurationError(
                "On-chain resolution is not configured for this API instance."
            )

        resolution_result = self.arbiter_client.resolve_challenge(
            audit_id=onchain_audit_id,
            upheld=upheld,
        )
        challenge = record["challenge"]
        challenge.update(
            {
                "status": resolution_result.resolution,
                "resolution_path": "manual_fallback",
                "resolution": resolution_result.resolution,
                "resolved_at": datetime.now(UTC).isoformat(),
                "resolved_by": resolved_by,
                "beneficiary_address": resolution_result.beneficiary_address,
                "payout_wei": resolution_result.payout_wei,
                "resolve_tx_hash": resolution_result.tx_hash,
                "resolve_tx_url": self.contract_config.transaction_url(
                    resolution_result.tx_hash
                ),
            }
        )
        record["status"] = "resolved"
        record["validation"] = self._submit_validation_response(record)
        self.store.write(audit_id, record)
        return record

    def get_validation_request_document(self, audit_id: str) -> dict[str, Any] | None:
        record = self.get_audit(audit_id)
        if record is None:
            return None
        validation = record.get("validation")
        if not isinstance(validation, dict) or not validation.get("request_hash"):
            return None
        return self._build_validation_request_document(record)

    def get_validation_response_document(self, audit_id: str) -> dict[str, Any] | None:
        record = self.get_audit(audit_id)
        if record is None:
            return None
        validation = record.get("validation")
        if not isinstance(validation, dict) or not validation.get("response_hash"):
            return None
        return self._build_validation_response_document(record)

    def _require_audit(self, audit_id: str) -> dict[str, Any]:
        record = self.get_audit(audit_id)
        if record is None:
            raise KeyError(audit_id)
        return record

    def _normalize_stored_record(self, record: dict[str, Any]) -> dict[str, Any]:
        normalized = deepcopy(record)
        record_id = normalized.get("id")
        if not isinstance(record_id, str) or not record_id:
            raise ValueError("stored audit record is missing its id")

        contract_address = normalized.get("contract_address")
        onchain = normalized.get("onchain")
        chain_id = onchain.get("chain_id") if isinstance(onchain, dict) else None
        submission = normalized.get("submission")
        if not isinstance(submission, dict):
            submission = {}
        submission_payload = dict(submission)
        if not submission_payload.get("contract_address") and contract_address:
            submission_payload["contract_address"] = contract_address
        if submission_payload.get("chain_id") is None and chain_id is not None:
            submission_payload["chain_id"] = chain_id
        if "input_kind" not in submission_payload:
            submission_payload["input_kind"] = "deployed_address"
        normalized["agent"] = self._normalize_agent(normalized.get("agent"))
        if isinstance(onchain, dict):
            onchain.setdefault("agent_name", str(normalized["agent"]["name"]))
            onchain.setdefault("agent_version", str(normalized["agent"]["version"]))
            normalized["onchain"] = onchain
        challenge = normalized.get("challenge")
        if isinstance(challenge, dict):
            normalized["challenge"] = self._normalize_challenge(challenge)
        validation = normalized.get("validation")
        if isinstance(validation, dict):
            normalized["validation"] = validation
        execution = normalized.get("execution")
        if isinstance(execution, dict):
            normalized["execution"] = execution
        normalized["submission"] = self._normalize_submission(submission_payload)
        normalized["contract_address"] = normalized["submission"]["contract_address"]

        normalized["report"] = self._normalize_report(
            normalized.get("report"),
            contract_address=normalized["contract_address"],
        )

        if normalized != record:
            self.store.write(record_id, normalized)
        return normalized

    def _submit_validation_request(self, record: dict[str, Any]) -> dict[str, Any] | None:
        validation = self._build_validation_seed(record)
        if validation is None:
            return None
        if self.validation_bridge is None:
            validation["status"] = "request_unavailable"
            validation["last_error"] = (
                "Validation registry is configured, but request submission is not enabled in this API instance."
            )
            return validation
        try:
            result = self.validation_bridge.submit_request(
                request_uri=str(validation["request_uri"]),
                request_hash=str(validation["request_hash"]),
            )
        except ValidationBridgeError as exc:
            validation["status"] = "request_failed"
            validation["last_error"] = str(exc)
            return validation

        validation.update(
            {
                "status": "requested",
                "request_tx_hash": result.tx_hash,
                "request_tx_url": self.contract_config.transaction_url(result.tx_hash),
                "validator_address": result.validator_address,
                "last_error": None,
            }
        )
        return validation

    def _submit_validation_response(self, record: dict[str, Any]) -> dict[str, Any] | None:
        validation = deepcopy(record.get("validation"))
        if not isinstance(validation, dict) or not validation.get("request_hash"):
            return None
        response_payload = self._build_validation_response_payload(record)
        if response_payload is None:
            return validation
        response_document = self._build_validation_response_document(record)
        response_hash = self._hash_payload(response_document)
        validation.update(
            {
                "response": response_payload["response"],
                "response_tag": response_payload["tag"],
                "response_uri": self._validation_response_uri(record["id"]),
                "response_hash": response_hash,
                "linked_resolution": response_payload["linked_resolution"],
                "linked_resolution_path": response_payload["linked_resolution_path"],
            }
        )
        if self.validation_bridge is None:
            validation["status"] = "response_unavailable"
            validation["last_error"] = (
                "Validation registry is configured, but response submission is not enabled in this API instance."
            )
            return validation
        try:
            result = self.validation_bridge.submit_response(
                request_hash=str(validation["request_hash"]),
                response=int(response_payload["response"]),
                response_uri=str(validation["response_uri"]),
                response_hash=response_hash,
                tag=str(response_payload["tag"]),
            )
        except ValidationBridgeError as exc:
            validation["status"] = "response_failed"
            validation["last_error"] = str(exc)
            return validation

        validation.update(
            {
                "status": "responded",
                "response_tx_hash": result.tx_hash,
                "response_tx_url": self.contract_config.transaction_url(result.tx_hash),
                "last_error": None,
            }
        )
        return validation

    def _build_validation_seed(self, record: dict[str, Any]) -> dict[str, Any] | None:
        if (
            not self.contract_config.validation_registry_address
            or self.contract_config.auditor_agent_id is None
            or not self.contract_config.validator_address
        ):
            return None
        request_document = self._build_validation_request_document(record)
        return {
            "status": "pending_request",
            "registry_address": self.contract_config.validation_registry_address,
            "source": self.contract_config.validation_bridge_source or "configured",
            "agent_id": self.contract_config.auditor_agent_id,
            "request_uri": self._validation_request_uri(record["id"]),
            "request_hash": self._hash_payload(request_document),
            "validator_address": self.contract_config.validator_address,
            "request_tx_hash": None,
            "request_tx_url": None,
            "response": None,
            "response_tag": None,
            "response_uri": None,
            "response_hash": None,
            "response_tx_hash": None,
            "response_tx_url": None,
            "linked_resolution": None,
            "linked_resolution_path": None,
            "last_error": None,
        }

    def _validation_request_uri(self, audit_id: str) -> str:
        return f"{self.contract_config.runtime_api_base_url}/audits/{audit_id}/validation/request"

    def _validation_response_uri(self, audit_id: str) -> str:
        return f"{self.contract_config.runtime_api_base_url}/audits/{audit_id}/validation/response"

    def _hash_payload(self, payload: dict[str, Any]) -> str:
        return "0x" + sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    def _build_validation_request_document(
        self, record: dict[str, Any]
    ) -> dict[str, Any]:
        onchain = record.get("onchain") or {}
        report = record["report"]
        return {
            "type": "https://eips.ethereum.org/EIPS/eip-8004#validation-request-v1",
            "requestType": "proof-of-audit.audit-claim",
            "auditRecordId": record["id"],
            "agentId": self.contract_config.auditor_agent_id,
            "agentRegistry": self.contract_config.auditor_agent_registry,
            "validationRegistry": self.contract_config.validation_registry_address,
            "validatorAddress": self.contract_config.validator_address,
            "claim": {
                "targetContract": record["contract_address"],
                "reportHash": report["report_hash"],
                "metadataHash": report["metadata_hash"],
                "summary": report["summary"],
                "maxSeverity": report["max_severity"],
                "findingCount": report["finding_count"],
            },
            "submission": record["submission"],
            "settlement": {
                "network": self.contract_config.network,
                "chainId": self.contract_config.chain_id,
                "proofOfAuditContract": self.contract_config.contract_address,
                "publishedAuditId": onchain.get("audit_id"),
                "publishTxHash": onchain.get("publish_tx_hash"),
                "stakeWei": onchain.get("stake_wei"),
            },
            "service": {
                "registrationUri": self.contract_config.auditor_registration_uri,
                "registrationEndpoint": (
                    f"{self.contract_config.runtime_api_base_url}/auditor/registration"
                ),
            },
        }

    def _build_validation_response_document(
        self, record: dict[str, Any]
    ) -> dict[str, Any]:
        validation = record["validation"]
        challenge = record.get("challenge") or {}
        response_payload = self._build_validation_response_payload(record)
        response = response_payload["response"] if response_payload else validation.get("response")
        tag = response_payload["tag"] if response_payload else validation.get("response_tag")
        return {
            "type": "https://eips.ethereum.org/EIPS/eip-8004#validation-response-v1",
            "auditRecordId": record["id"],
            "agentId": self.contract_config.auditor_agent_id,
            "requestHash": validation["request_hash"],
            "validationRegistry": self.contract_config.validation_registry_address,
            "validatorAddress": validation["validator_address"],
            "response": response,
            "tag": tag,
            "outcome": {
                "auditStatus": record["status"],
                "challengeStatus": challenge.get("status"),
                "resolution": challenge.get("resolution"),
                "resolutionPath": challenge.get("resolution_path"),
                "resolveTxHash": challenge.get("resolve_tx_hash"),
            },
            "evidence": {
                "proofUri": challenge.get("proof_uri"),
                "verificationStatus": challenge.get("verification_status"),
                "verificationSummary": challenge.get("verification_summary"),
                "verificationDetail": challenge.get("verification_detail"),
            },
        }

    def _build_validation_response_payload(
        self, record: dict[str, Any]
    ) -> dict[str, Any] | None:
        challenge = record.get("challenge")
        if not isinstance(challenge, dict):
            return None
        resolution = str(challenge.get("resolution") or "")
        resolution_path = str(challenge.get("resolution_path") or "")
        if resolution == "rejected":
            return {
                "response": 100,
                "tag": "claim-confirmed",
                "linked_resolution": resolution,
                "linked_resolution_path": resolution_path,
            }
        if resolution == "upheld":
            return {
                "response": 0,
                "tag": "claim-refuted",
                "linked_resolution": resolution,
                "linked_resolution_path": resolution_path,
            }
        return None

    def _normalize_challenge(self, challenge: Any) -> dict[str, Any]:
        payload = deepcopy(challenge) if isinstance(challenge, dict) else {}
        if payload.get("resolution_path") in {"deterministic", "manual_fallback"}:
            return payload

        resolved_by = str(payload.get("resolved_by") or "")
        status = str(payload.get("status") or "opened")
        verification_status = str(payload.get("verification_status") or "")

        if resolved_by == "deterministic-verifier" or (
            verification_status == "verified" and status in {"upheld", "rejected"}
        ):
            payload["resolution_path"] = "deterministic"
        else:
            payload["resolution_path"] = "manual_fallback"
        return payload

    def _normalize_agent(self, agent: Any) -> dict[str, object]:
        payload = agent if isinstance(agent, dict) else {}
        defaults = self.contract_config.auditor.to_dict()
        normalized = dict(defaults)
        for key, value in payload.items():
            if key == "capabilities" and isinstance(value, list):
                normalized[key] = [str(item) for item in value]
            elif value is not None:
                normalized[key] = value
        return normalized

    def _normalize_report(
        self, report: Any, *, contract_address: str
    ) -> dict[str, Any]:
        payload = deepcopy(report) if isinstance(report, dict) else {}
        findings = payload.get("findings")
        if not isinstance(findings, list):
            findings = []

        normalized_findings: list[dict[str, Any]] = []
        for index, finding in enumerate(findings):
            normalized_findings.append(
                self._normalize_finding(
                    finding,
                    benchmark_id=str(payload.get("benchmark_id", "unknown")),
                    report_confidence=str(payload.get("confidence", "medium")),
                    index=index,
                )
            )

        payload["benchmark_id"] = str(payload.get("benchmark_id", "unknown"))
        payload["contract_address"] = str(payload.get("contract_address") or contract_address)
        payload["summary"] = str(payload.get("summary", "No summary available."))
        payload["findings"] = normalized_findings
        payload["supported_checks"] = self._normalize_supported_checks(
            payload.get("supported_checks")
        )
        payload["confidence"] = str(payload.get("confidence", "medium"))
        payload["finding_count"] = len(normalized_findings)
        payload["severity_breakdown"] = self._build_severity_breakdown(normalized_findings)
        payload["max_severity"] = self._max_severity(normalized_findings)
        return payload

    def _normalize_finding(
        self,
        finding: Any,
        *,
        benchmark_id: str,
        report_confidence: str,
        index: int,
    ) -> dict[str, Any]:
        payload = deepcopy(finding) if isinstance(finding, dict) else {}
        title = str(payload.get("title") or f"Finding {index + 1}")
        detector = str(payload.get("detector") or "deterministic.legacy")
        severity = str(payload.get("severity") or "info").lower()
        payload["title"] = title
        payload["severity"] = severity
        payload["detector"] = detector
        payload["description"] = str(payload.get("description") or "No description provided.")
        payload["recommendation"] = str(
            payload.get("recommendation")
            or "Review the reported issue and patch before deployment."
        )
        payload["confidence"] = str(payload.get("confidence") or report_confidence or "medium")
        payload["category"] = str(
            payload.get("category") or self._infer_category(detector=detector, title=title)
        )
        payload["impact"] = str(
            payload.get("impact")
            or self._default_impact(severity=severity, description=payload["description"])
        )
        payload["finding_id"] = str(
            payload.get("finding_id")
            or self._make_finding_id(
                benchmark_id=benchmark_id,
                detector=detector,
                title=title,
                index=index,
            )
        )
        return payload

    def _normalize_supported_checks(self, checks: Any) -> list[str]:
        if isinstance(checks, list) and checks:
            return [str(check) for check in checks]
        return ["reentrancy", "access_control", "unchecked_external_call"]

    def _build_severity_breakdown(
        self, findings: list[dict[str, Any]]
    ) -> dict[str, int]:
        breakdown = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
        for finding in findings:
            severity = str(finding.get("severity", "info")).lower()
            breakdown[severity] = breakdown.get(severity, 0) + 1
        return breakdown

    def _max_severity(self, findings: list[dict[str, Any]]) -> int:
        ranking = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
        if not findings:
            return 0
        return max(ranking.get(str(finding.get("severity", "info")).lower(), 0) for finding in findings)

    def _infer_category(self, *, detector: str, title: str) -> str:
        lowered = f"{detector} {title}".lower()
        if "reentrancy" in lowered:
            return "reentrancy"
        if "access" in lowered or "owner" in lowered or "admin" in lowered:
            return "access_control"
        if "unchecked" in lowered or "external" in lowered or "call" in lowered:
            return "unchecked_external_call"
        return "general"

    def _default_impact(self, *, severity: str, description: str) -> str:
        if severity == "critical":
            return "Critical issue with severe loss or takeover risk."
        if severity == "high":
            return "High-risk issue that can likely lead to direct asset loss or control abuse."
        if severity == "medium":
            return "Moderate-risk issue that can break assumptions or degrade protocol safety."
        if severity == "low":
            return "Low-risk issue with limited direct impact."
        if description:
            return description
        return "Informational issue that should still be reviewed."

    def _make_finding_id(
        self, *, benchmark_id: str, detector: str, title: str, index: int
    ) -> str:
        normalized_title = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        normalized_detector = detector.split(".")[-1].lower()
        suffix = normalized_title or f"finding-{index + 1}"
        return f"{benchmark_id}.{normalized_detector}.{suffix}"

    def _normalize_submission(self, submission: dict[str, Any]) -> dict[str, Any]:
        input_kind = submission.get("input_kind", "deployed_address")
        chain_id = submission.get("chain_id")
        entry_contract = submission.get("entry_contract")
        source_bundle_uri = submission.get("source_bundle_uri")
        source_bundle_label = submission.get("source_bundle_label")
        repository_url = submission.get("repository_url")
        fixture_id = submission.get("fixture_id")

        if input_kind == "demo_fixture":
            fixture = self.worker.require_fixture(fixture_id)
            return {
                "input_kind": "demo_fixture",
                "chain_id": chain_id or self.contract_config.chain_id,
                "contract_address": fixture.address,
                "fixture_id": fixture.fixture_id,
                "entry_contract": entry_contract or fixture.entry_contract,
                "source_bundle_uri": source_bundle_uri,
                "source_bundle_label": source_bundle_label or fixture.label,
                "repository_url": repository_url,
            }

        if input_kind == "source_bundle":
            if not source_bundle_uri:
                raise ValueError("source_bundle_uri is required for source_bundle submissions")
            return {
                "input_kind": "source_bundle",
                "chain_id": chain_id,
                "contract_address": self.worker.synthetic_contract_address(
                    source_bundle_uri,
                    entry_contract=entry_contract,
                ),
                "fixture_id": fixture_id,
                "entry_contract": entry_contract,
                "source_bundle_uri": source_bundle_uri,
                "source_bundle_label": source_bundle_label,
                "repository_url": repository_url,
            }

        if input_kind == "repository_url":
            if not repository_url:
                raise ValueError("repository_url is required for repository_url submissions")
            return {
                "input_kind": "repository_url",
                "chain_id": chain_id,
                "contract_address": f"0x{sha256(repository_url.encode('utf-8')).hexdigest()[:40]}",
                "fixture_id": fixture_id,
                "entry_contract": entry_contract,
                "source_bundle_uri": source_bundle_uri,
                "source_bundle_label": source_bundle_label,
                "repository_url": repository_url,
            }

        contract_address = submission.get("contract_address")
        if not contract_address:
            raise ValueError("contract_address is required for deployed_address submissions")
        return {
            "input_kind": "deployed_address",
            "chain_id": chain_id or self.contract_config.chain_id,
            "contract_address": contract_address.lower(),
            "fixture_id": fixture_id,
            "entry_contract": entry_contract,
            "source_bundle_uri": source_bundle_uri,
            "source_bundle_label": source_bundle_label,
            "repository_url": repository_url,
        }
