from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
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
from proof_of_audit_api.reputation_bridge import (
    OnchainReputationSnapshot,
    ReputationBridgeError,
    ReputationRegistryBridge,
)
from proof_of_audit_api.validation_bridge import (
    ValidationBridgeError,
    ValidationRegistryBridge,
)
from proof_of_audit_agent.challenge_claim_extractor import (
    CommandBackedChallengeClaimExtractor,
)
from proof_of_audit_agent.challenge_verifier import (
    ChallengeVerifierStrategy,
    EvidenceContext,
    ProofUriChallengeVerifier,
)
from proof_of_audit_agent.executable_evidence_verifier import (
    ExecutableEvidenceVerifier,
)
from proof_of_audit_agent.executable_evidence_resolver import (
    EvidenceResolutionError,
    ExecutableEvidenceResolver,
)
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
        reputation_bridge: ReputationRegistryBridge | None = None,
        challenge_verifiers: dict[str, ChallengeVerifierStrategy] | None = None,
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
        executable_verifier = ExecutableEvidenceVerifier(
            extractor=self._build_challenge_claim_extractor()
        )
        self.challenge_verifiers = challenge_verifiers or {
            "deterministic_fixture": ProofUriChallengeVerifier(),
            "executable_test": executable_verifier,
        }
        self.evidence_resolver = ExecutableEvidenceResolver()
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
        self.reputation_bridge = reputation_bridge or ReputationRegistryBridge.from_config_if_ready(
            self.contract_config
        )

    def _build_challenge_claim_extractor(
        self,
    ) -> CommandBackedChallengeClaimExtractor | None:
        command = self.contract_config.challenge_claim_extractor_command
        if not command:
            return None
        return CommandBackedChallengeClaimExtractor(
            command=command,
            provider=self.contract_config.challenge_claim_extractor_provider,
            model=self.contract_config.challenge_claim_extractor_model,
            min_confidence=self.contract_config.challenge_claim_extractor_min_confidence,
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
        auditor_service = self._require_submission_service(
            normalized_submission.get("service_id"),
            normalized_submission["input_kind"],
        )
        auditor_profile = self._auditor_profile_payload_for_service(
            auditor_service.service_id
        )
        audit_id = str(uuid4())
        execution_result = self.worker.run_submission(
            audit_id=audit_id,
            **self._worker_submission_payload(normalized_submission),
        )
        target_key = self._normalize_target_key(normalized_submission["contract_address"])
        record = {
            "id": audit_id,
            "agent": auditor_profile,
            "auditor_service": auditor_service.to_dict(),
            "contract_address": normalized_submission["contract_address"],
            "target_key": target_key,
            "target_auditor_key": self._target_auditor_key(
                target_key, auditor_service.service_id
            ),
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
            "reputation_trail": None,
        }
        self.store.write(audit_id, record)
        return self.get_audit(audit_id) or record

    def get_audit(self, audit_id: str) -> dict[str, Any] | None:
        records = self._all_normalized_records()
        reputation_index = self._build_reputation_index(records)
        for record in records:
            if record["id"] == audit_id:
                return self._attach_reputation(record, reputation_index)
        return None

    def list_audits(self, contract_address: str | None = None) -> list[dict[str, Any]]:
        all_records = self._all_normalized_records()
        reputation_index = self._build_reputation_index(all_records)
        records = (
            [
                record
                for record in all_records
                if record["target_key"] == self._normalize_target_key(contract_address)
            ]
            if contract_address
            else all_records
        )
        records = [self._attach_reputation(record, reputation_index) for record in records]
        return sorted(records, key=lambda record: record["created_at"], reverse=True)

    def list_target_claims(self, contract_address: str) -> list[dict[str, Any]]:
        return self.list_audits(contract_address=contract_address)

    def build_target_comparison(self, contract_address: str) -> dict[str, Any]:
        items = self.list_target_claims(contract_address)
        return {
            "target_contract": self._normalize_target_key(contract_address),
            "target_key": self._normalize_target_key(contract_address),
            "summary": {
                "claim_count": len(items),
                "published_count": sum(1 for item in items if item["status"] == "published"),
                "challenged_count": sum(
                    1 for item in items if item["status"] == "challenged"
                ),
                "resolved_count": sum(1 for item in items if item["status"] == "resolved"),
                "max_severity": max(
                    (int(item["report"]["max_severity"]) for item in items),
                    default=0,
                ),
            },
            "items": items,
        }

    def list_demo_fixtures(self) -> list[dict[str, Any]]:
        return self.worker.list_demo_fixtures()

    def list_auditor_services(self) -> list[dict[str, Any]]:
        reputation_index = self._build_reputation_index(self._all_normalized_records())
        return [
            self._build_service_payload(entry.service, reputation_index)
            for entry in self.contract_config.auditor_directory_entries
        ]

    def get_auditor_service(self, service_id: str) -> dict[str, Any] | None:
        service = self.contract_config.auditor_service_by_id(service_id)
        if service is None:
            return None
        reputation_index = self._build_reputation_index(self._all_normalized_records())
        return self._build_service_payload(service, reputation_index)

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
        agent = self._record_agent_profile(record)
        agent_identity = agent_identity or str(agent.get("id") or self.contract_config.auditor.id)
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
            "published_at": datetime.now(UTC).isoformat(),
            "network": self.contract_config.network,
            "chain_id": publish_result.chain_id,
            "contract_address": self.contract_config.contract_address,
            "explorer_base_url": self.contract_config.explorer_base_url,
            "agent_identity": agent_identity,
            "agent_name": str(agent.get("name") or self.contract_config.auditor.name),
            "agent_version": str(
                agent.get("version") or self.contract_config.auditor.version
            ),
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
        record["reputation_trail"] = self._submit_reputation_claim(record)
        self.store.write(audit_id, record)
        return record

    def challenge_audit(
        self,
        audit_id: str,
        proof_uri: str,
        challenger: str,
        evidence_type: str = "deterministic_fixture",
        execution_env: str | None = None,
        evidence_manifest: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        record = self._require_audit(audit_id)
        if record["challenge"] is not None or record["status"] in {"challenged", "resolved"}:
            raise ValueError("audit has already been challenged")
        if record["status"] != "published" or record["onchain"] is None:
            raise ValueError("audit must be published before challenge")
        if (
            evidence_type == "executable_test"
            and record["submission"]["input_kind"] != "deployed_address"
        ):
            raise ValueError(
                "executable_test challenge evidence is only supported for deployed_address audits"
            )
        onchain_audit_id = record["onchain"].get("audit_id")
        if not isinstance(onchain_audit_id, int):
            raise ValueError("published audit is missing its on-chain audit id")
        if self.publisher is None:
            raise OnchainConfigurationError(
                "On-chain challenge submission is not configured for this API instance."
            )
        verifier = self.challenge_verifiers.get(evidence_type)
        if verifier is None:
            raise ValueError(f"unsupported evidence_type: {evidence_type}")
        evidence_hash = self._build_committed_evidence_hash(
            proof_uri=proof_uri,
            evidence_type=evidence_type,
            execution_env=execution_env,
            evidence_manifest=evidence_manifest,
            chain_id=int(record["onchain"].get("chain_id") or self.contract_config.chain_id),
        )

        challenge_result = self.publisher.challenge_audit(
            audit_id=onchain_audit_id,
            evidence_hash=evidence_hash,
            challenge_bond_wei=self.contract_config.required_challenge_bond_wei,
        )
        verification_result = verifier.verify(
            EvidenceContext(
                proof_uri=proof_uri,
                benchmark_id=str(record["report"].get("benchmark_id") or "unknown"),
                target_contract=record["contract_address"],
                published_report=deepcopy(record["report"]),
                evidence_type=evidence_type,
                execution_env=execution_env,
                evidence_manifest=deepcopy(evidence_manifest),
                chain_id=int(
                    record["onchain"].get("chain_id") or self.contract_config.chain_id
                ),
                rpc_url=self.contract_config.rpc_url,
                committed_evidence_hash=evidence_hash,
            )
        )
        challenge_record = {
            "challenger": challenger,
            "challenger_address": challenge_result.challenger_address,
            "proof_uri": proof_uri,
            "evidence_hash": challenge_result.evidence_hash,
            "evidence_type": evidence_type,
            "execution_env": execution_env,
            "evidence_manifest": deepcopy(evidence_manifest),
            "submitted_at": datetime.now(UTC).isoformat(),
            "verifier": verification_result.verifier,
            "status": "opened",
            "resolution_path": "manual_fallback",
            "verification_status": verification_result.status,
            "verification_summary": verification_result.summary,
            "verification_detail": verification_result.detail,
            "verification_case_id": verification_result.case_id,
            "advisory_verdict": (
                verification_result.resolution if verification_result.advisory_only else None
            ),
            "execution_log": verification_result.execution_log,
            "matched_findings": verification_result.matched_findings,
            "unmatched_findings": verification_result.unmatched_findings,
            "verification_dossier": self._verification_dossier_payload(
                verification_result=verification_result,
                challenge_defaults={
                    "evidence_type": evidence_type,
                    "execution_env": execution_env,
                    "proof_uri": proof_uri,
                    "evidence_hash": challenge_result.evidence_hash,
                    "matched_findings": verification_result.matched_findings,
                    "unmatched_findings": verification_result.unmatched_findings,
                    "advisory_verdict": (
                        verification_result.resolution
                        if verification_result.advisory_only
                        else None
                    ),
                    "verification_status": verification_result.status,
                    "verifier": verification_result.verifier,
                },
            ),
            "challenge_hash": challenge_result.evidence_hash,
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
            and not verification_result.advisory_only
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
            record["reputation_trail"] = self._submit_reputation_resolution(record)
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
        record["reputation_trail"] = self._submit_reputation_resolution(record)
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

    def get_reputation_claim_document(self, audit_id: str) -> dict[str, Any] | None:
        record = self.get_audit(audit_id)
        if record is None:
            return None
        reputation_trail = record.get("reputation_trail")
        if not isinstance(reputation_trail, dict) or not reputation_trail.get("claim_hash"):
            return None
        return self._build_reputation_claim_document(record)

    def get_reputation_resolution_document(self, audit_id: str) -> dict[str, Any] | None:
        record = self.get_audit(audit_id)
        if record is None:
            return None
        reputation_trail = record.get("reputation_trail")
        if not isinstance(reputation_trail, dict) or not reputation_trail.get("resolution_hash"):
            return None
        return self._build_reputation_resolution_document(record)

    def get_auditor_reputation(self, service_id: str) -> dict[str, Any] | None:
        service = self.get_auditor_service(service_id)
        if service is None:
            return None
        reputation = service.get("reputation")
        if not isinstance(reputation, dict):
            return None
        return {
            "service_id": service_id,
            "reputation": deepcopy(reputation),
        }

    def list_challenger_events(self, limit: int = 50) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for record in self._all_normalized_records():
            items.extend(self._challenger_events_for_record(record))
        items.sort(key=lambda item: str(item["event_timestamp"]), reverse=True)
        return items[:limit]

    def _require_audit(self, audit_id: str) -> dict[str, Any]:
        record = self.store.read(audit_id)
        if record is None:
            raise KeyError(audit_id)
        return self._normalize_stored_record(record)

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
        if not submission_payload.get("service_id"):
            stored_service = normalized.get("auditor_service")
            if isinstance(stored_service, dict) and stored_service.get("service_id"):
                submission_payload["service_id"] = stored_service.get("service_id")
            elif isinstance(normalized.get("agent"), dict) and normalized["agent"].get("id"):
                submission_payload["service_id"] = normalized["agent"].get("id")
            else:
                submission_payload["service_id"] = self.contract_config.auditor_service.service_id
        normalized["submission"] = self._normalize_submission(submission_payload)
        normalized_service = self._normalize_auditor_service(
            normalized.get("auditor_service"),
            service_id=str(normalized["submission"]["service_id"]),
        )
        normalized["auditor_service"] = normalized_service
        normalized["agent"] = self._normalize_agent(
            normalized.get("agent"),
            default_agent=self._auditor_profile_payload_for_service(
                str(normalized_service["service_id"])
            ),
        )
        if isinstance(onchain, dict):
            onchain.setdefault("published_at", normalized.get("created_at"))
            onchain.setdefault("agent_name", str(normalized["agent"]["name"]))
            onchain.setdefault("agent_version", str(normalized["agent"]["version"]))
            normalized["onchain"] = onchain
        challenge = normalized.get("challenge")
        if isinstance(challenge, dict):
            normalized["challenge"] = self._normalize_challenge(challenge)
        validation = normalized.get("validation")
        if isinstance(validation, dict):
            normalized["validation"] = validation
        reputation_trail = normalized.get("reputation_trail")
        if isinstance(reputation_trail, dict):
            normalized["reputation_trail"] = reputation_trail
        execution = normalized.get("execution")
        if isinstance(execution, dict):
            normalized["execution"] = execution
        normalized["contract_address"] = normalized["submission"]["contract_address"]
        normalized["target_key"] = self._normalize_target_key(normalized["contract_address"])
        normalized["target_auditor_key"] = self._target_auditor_key(
            normalized["target_key"],
            str(normalized["auditor_service"]["service_id"]),
        )

        normalized["report"] = self._normalize_report(
            normalized.get("report"),
            contract_address=normalized["contract_address"],
        )

        if normalized != record:
            self.store.write(record_id, normalized)
        return normalized

    def _all_normalized_records(self) -> list[dict[str, Any]]:
        return [self._normalize_stored_record(record) for record in self.store.list_all()]

    def _build_reputation_index(
        self, records: list[dict[str, Any]]
    ) -> dict[str, dict[str, Any]]:
        index: dict[str, dict[str, Any]] = {}
        for record in records:
            agent = record.get("agent")
            auditor_id = (
                str(agent.get("id"))
                if isinstance(agent, dict) and agent.get("id") is not None
                else self.contract_config.auditor.id
            )
            reputation = index.setdefault(auditor_id, self._default_reputation())
            status = str(record.get("status") or "draft")
            if status == "draft":
                reputation["draft_claim_count"] += 1
            else:
                reputation["published_claim_count"] += 1
            if status == "challenged":
                reputation["open_challenge_count"] += 1
            challenge = record.get("challenge")
            if status == "resolved" and isinstance(challenge, dict):
                reputation["resolved_challenge_count"] += 1
                resolution = str(challenge.get("resolution") or "")
                if resolution == "rejected":
                    reputation["challenge_rejected_count"] += 1
                elif resolution == "upheld":
                    reputation["challenge_upheld_count"] += 1
                resolved_at = challenge.get("resolved_at")
                if (
                    isinstance(resolved_at, str)
                    and resolved_at
                    and (
                        reputation["last_resolved_at"] is None
                        or resolved_at > reputation["last_resolved_at"]
                    )
                ):
                    reputation["last_resolved_at"] = resolved_at

        for reputation in index.values():
            resolved_count = int(reputation["resolved_challenge_count"])
            rejected_count = int(reputation["challenge_rejected_count"])
            if resolved_count == 0:
                reputation["score"] = 50
                reputation["band"] = "provisional"
            else:
                reputation["score"] = round(100 * rejected_count / resolved_count)
                if reputation["score"] >= 75:
                    reputation["band"] = "trusted"
                elif reputation["score"] >= 40:
                    reputation["band"] = "mixed"
                else:
                    reputation["band"] = "contested"
        onchain_reputation = self._load_onchain_reputation()
        if onchain_reputation is not None:
            index[self.contract_config.auditor.id] = self._apply_onchain_reputation_snapshot(
                index.get(self.contract_config.auditor.id, self._default_reputation()),
                onchain_reputation,
            )
        return index

    def _default_reputation(self) -> dict[str, Any]:
        return {
            "score": 50,
            "band": "provisional",
            "resolved_challenge_count": 0,
            "challenge_rejected_count": 0,
            "challenge_upheld_count": 0,
            "open_challenge_count": 0,
            "published_claim_count": 0,
            "draft_claim_count": 0,
            "last_resolved_at": None,
            "source": None,
            "registry_address": None,
            "agent_id": None,
            "total_stake_wei": None,
            "last_update": None,
            "formula": (
                "Neutral 50 when there are no resolved challenges; otherwise "
                "round(100 * challenge_rejected_count / resolved_challenge_count)."
            ),
        }

    def _load_onchain_reputation(self) -> OnchainReputationSnapshot | None:
        if self.reputation_bridge is None or self.contract_config.auditor_agent_id is None:
            return None
        try:
            return self.reputation_bridge.get_reputation(self.contract_config.auditor_agent_id)
        except ReputationBridgeError:
            return None

    def _apply_onchain_reputation_snapshot(
        self,
        reputation: dict[str, Any],
        snapshot: OnchainReputationSnapshot,
    ) -> dict[str, Any]:
        enriched = deepcopy(reputation)
        enriched["score"] = snapshot.score
        if snapshot.resolved_challenges == 0:
            enriched["band"] = "provisional"
        elif snapshot.score >= 75:
            enriched["band"] = "trusted"
        elif snapshot.score >= 40:
            enriched["band"] = "mixed"
        else:
            enriched["band"] = "contested"
        enriched["resolved_challenge_count"] = snapshot.resolved_challenges
        enriched["challenge_rejected_count"] = snapshot.challenge_rejected_count
        enriched["challenge_upheld_count"] = snapshot.challenge_upheld_count
        enriched["published_claim_count"] = snapshot.total_claims
        enriched["source"] = snapshot.source
        enriched["registry_address"] = snapshot.registry_address
        enriched["agent_id"] = snapshot.agent_id
        enriched["total_stake_wei"] = snapshot.total_stake_wei
        enriched["last_update"] = snapshot.last_update
        return enriched

    def _attach_reputation(
        self, record: dict[str, Any], reputation_index: dict[str, dict[str, Any]]
    ) -> dict[str, Any]:
        enriched = deepcopy(record)
        agent = deepcopy(enriched.get("agent", {}))
        auditor_id = str(agent.get("id") or self.contract_config.auditor.id)
        agent["reputation"] = deepcopy(
            reputation_index.get(auditor_id, self._default_reputation())
        )
        enriched["agent"] = agent
        auditor_service = deepcopy(enriched.get("auditor_service", {}))
        service_id = str(
            auditor_service.get("service_id")
            or enriched.get("submission", {}).get("service_id")
            or self.contract_config.auditor_service.service_id
        )
        if service_id:
            service_reputation_id = self._auditor_id_for_service(service_id)
            auditor_service["reputation"] = deepcopy(
                reputation_index.get(service_reputation_id, self._default_reputation())
            )
            enriched["auditor_service"] = auditor_service
        return enriched

    def _build_service_payload(
        self, service: Any, reputation_index: dict[str, dict[str, Any]]
    ) -> dict[str, Any]:
        payload = service.to_dict()
        auditor_id = self._auditor_id_for_service(service.service_id)
        payload["reputation"] = deepcopy(
            reputation_index.get(auditor_id, self._default_reputation())
        )
        return payload

    def _challenger_events_for_record(self, record: dict[str, Any]) -> list[dict[str, Any]]:
        onchain = record.get("onchain")
        if not isinstance(onchain, dict) or not onchain.get("audit_id"):
            return []

        events: list[dict[str, Any]] = []
        published_at = str(onchain.get("published_at") or record.get("created_at") or "")
        if published_at:
            events.append(
                self._build_challenger_event(
                    record,
                    event_kind="audit_published",
                    event_suffix="published",
                    event_timestamp=published_at,
                )
            )

        challenge = record.get("challenge")
        if isinstance(challenge, dict):
            submitted_at = str(challenge.get("submitted_at") or "")
            if submitted_at:
                events.append(
                    self._build_challenger_event(
                        record,
                        event_kind="challenge_opened",
                        event_suffix="challenge-opened",
                        event_timestamp=submitted_at,
                    )
                )
            resolved_at = str(challenge.get("resolved_at") or "")
            if resolved_at:
                events.append(
                    self._build_challenger_event(
                        record,
                        event_kind="challenge_resolved",
                        event_suffix="challenge-resolved",
                        event_timestamp=resolved_at,
                    )
                )
        return events

    def _build_challenger_event(
        self,
        record: dict[str, Any],
        *,
        event_kind: str,
        event_suffix: str,
        event_timestamp: str,
    ) -> dict[str, Any]:
        onchain = record.get("onchain") or {}
        challenge = record.get("challenge") or {}
        report = record["report"]
        agent = self._record_agent_profile(record)
        service = self._record_auditor_service(record)
        publish_timestamp = str(onchain.get("published_at") or record.get("created_at") or "")
        return {
            "event_id": f"{record['id']}::{event_suffix}",
            "event_kind": event_kind,
            "event_timestamp": event_timestamp,
            "audit_id": record["id"],
            "published_audit_id": onchain.get("audit_id"),
            "service_id": str(
                service.get("service_id")
                or record.get("submission", {}).get("service_id")
                or self.contract_config.auditor_service.service_id
            ),
            "auditor_id": str(agent.get("id") or self.contract_config.auditor.id),
            "auditor_name": str(agent.get("name") or self.contract_config.auditor.name),
            "target_contract": record["contract_address"],
            "target_key": record["target_key"],
            "publish_timestamp": publish_timestamp or None,
            "challenge_window_end": self._challenge_window_end(publish_timestamp),
            "current_state": str(record.get("status") or "draft"),
            "report_hash": str(report.get("report_hash") or ""),
            "metadata_hash": str(report.get("metadata_hash") or ""),
            "summary": str(report.get("summary") or ""),
            "max_severity": int(report.get("max_severity") or 0),
            "finding_count": int(report.get("finding_count") or len(report.get("findings") or [])),
            "publish_tx_hash": onchain.get("publish_tx_hash"),
            "publish_tx_url": onchain.get("publish_tx_url"),
            "challenge_tx_hash": challenge.get("challenge_tx_hash"),
            "challenge_tx_url": challenge.get("challenge_tx_url"),
            "resolve_tx_hash": challenge.get("resolve_tx_hash"),
            "resolve_tx_url": challenge.get("resolve_tx_url"),
            "resolution": challenge.get("resolution"),
        }

    def _challenge_window_end(self, publish_timestamp: str) -> str | None:
        if not publish_timestamp:
            return None
        try:
            published_at = datetime.fromisoformat(publish_timestamp)
        except ValueError:
            return None
        return (
            published_at + timedelta(seconds=self.contract_config.challenge_window_seconds)
        ).isoformat()

    def _auditor_id_for_service(self, service_id: str) -> str:
        if service_id == self.contract_config.auditor_service.service_id:
            return self.contract_config.auditor.id
        registration = self.contract_config.auditor_registration_document_by_service_id(
            service_id
        )
        if isinstance(registration, dict):
            extension = registration.get("x-proof-of-audit")
            if isinstance(extension, dict):
                extension_id = extension.get("id")
                if isinstance(extension_id, str) and extension_id.strip():
                    return extension_id.strip()
        return service_id.strip()

    def _submit_reputation_claim(self, record: dict[str, Any]) -> dict[str, Any] | None:
        reputation_trail = self._build_reputation_seed(record)
        if reputation_trail is None:
            return None
        if self.reputation_bridge is None:
            reputation_trail["status"] = "claim_unavailable"
            reputation_trail["last_error"] = (
                "Reputation registry is configured, but claim submission is not enabled in this API instance."
            )
            return reputation_trail
        try:
            result = self.reputation_bridge.submit_claim(
                claim_uri=str(reputation_trail["claim_uri"]),
                claim_hash=str(reputation_trail["claim_hash"]),
                stake_wei=int(reputation_trail["stake_wei"]),
            )
        except ReputationBridgeError as exc:
            reputation_trail["status"] = "claim_failed"
            reputation_trail["last_error"] = str(exc)
            return reputation_trail

        reputation_trail.update(
            {
                "status": "claim_recorded",
                "claim_tx_hash": result.tx_hash,
                "claim_tx_url": self.contract_config.transaction_url(result.tx_hash),
                "last_error": None,
            }
        )
        return reputation_trail

    def _submit_reputation_resolution(self, record: dict[str, Any]) -> dict[str, Any] | None:
        reputation_trail = deepcopy(record.get("reputation_trail"))
        if not isinstance(reputation_trail, dict) or not reputation_trail.get("claim_hash"):
            return None
        resolution_document = self._build_reputation_resolution_document(record)
        resolution_hash = self._hash_payload(resolution_document)
        claim_confirmed = self._claim_confirmed(record)
        if claim_confirmed is None:
            return reputation_trail
        reputation_trail.update(
            {
                "claim_confirmed": claim_confirmed,
                "resolution_uri": self._reputation_resolution_uri(record["id"]),
                "resolution_hash": resolution_hash,
                "linked_resolution": str(
                    (record.get("challenge") or {}).get("resolution") or ""
                )
                or None,
            }
        )
        if self.reputation_bridge is None:
            reputation_trail["status"] = "resolution_unavailable"
            reputation_trail["last_error"] = (
                "Reputation registry is configured, but resolution submission is not enabled in this API instance."
            )
            return reputation_trail
        try:
            result = self.reputation_bridge.submit_resolution(
                claim_hash=str(reputation_trail["claim_hash"]),
                claim_confirmed=claim_confirmed,
                resolution_uri=str(reputation_trail["resolution_uri"]),
            )
        except ReputationBridgeError as exc:
            reputation_trail["status"] = "resolution_failed"
            reputation_trail["last_error"] = str(exc)
            return reputation_trail

        reputation_trail.update(
            {
                "status": "resolution_recorded",
                "resolution_tx_hash": result.tx_hash,
                "resolution_tx_url": self.contract_config.transaction_url(result.tx_hash),
                "last_error": None,
            }
        )
        return reputation_trail

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

    def _build_reputation_seed(self, record: dict[str, Any]) -> dict[str, Any] | None:
        agent_id = self._record_agent_id(record)
        if (
            not self._record_reputation_registry_address(record)
            or agent_id is None
        ):
            return None
        onchain = record.get("onchain")
        if not isinstance(onchain, dict):
            return None
        claim_document = self._build_reputation_claim_document(record)
        return {
            "status": "pending_claim",
            "registry_address": self._record_reputation_registry_address(record),
            "source": self._record_reputation_source(record) or "configured",
            "agent_id": agent_id,
            "claim_uri": self._reputation_claim_uri(record["id"]),
            "claim_hash": self._hash_payload(claim_document),
            "stake_wei": int(onchain.get("stake_wei") or 0),
            "claim_tx_hash": None,
            "claim_tx_url": None,
            "claim_confirmed": None,
            "resolution_uri": None,
            "resolution_hash": None,
            "resolution_tx_hash": None,
            "resolution_tx_url": None,
            "linked_resolution": None,
            "last_error": None,
        }

    def _reputation_claim_uri(self, audit_id: str) -> str:
        return f"{self.contract_config.runtime_api_base_url}/audits/{audit_id}/reputation/claim"

    def _reputation_resolution_uri(self, audit_id: str) -> str:
        return (
            f"{self.contract_config.runtime_api_base_url}/audits/{audit_id}/reputation/resolution"
        )

    def _build_reputation_claim_document(
        self, record: dict[str, Any]
    ) -> dict[str, Any]:
        onchain = record.get("onchain") or {}
        report = record["report"]
        service = self._record_auditor_service(record)
        return {
            "type": "https://github.com/akoita/proof-of-audit#reputation-claim-v1",
            "auditRecordId": record["id"],
            "agentId": self._record_agent_id(record),
            "agentRegistry": self._record_agent_registry(record),
            "reputationRegistry": self._record_reputation_registry_address(record),
            "claim": {
                "targetContract": record["contract_address"],
                "reportHash": report["report_hash"],
                "metadataHash": report["metadata_hash"],
                "publishTxHash": onchain.get("publish_tx_hash"),
                "publishedAuditId": onchain.get("audit_id"),
                "stakeWei": onchain.get("stake_wei"),
            },
            "service": {
                "registrationUri": service.get("registration_uri"),
                "registrationEndpoint": (
                    f"{self.contract_config.runtime_api_base_url}"
                    f"{service.get('registration_endpoint') or '/auditor/registration'}"
                ),
            },
        }

    def _build_reputation_resolution_document(
        self, record: dict[str, Any]
    ) -> dict[str, Any]:
        challenge = record.get("challenge") or {}
        reputation_trail = record.get("reputation_trail") or {}
        return {
            "type": "https://github.com/akoita/proof-of-audit#reputation-resolution-v1",
            "auditRecordId": record["id"],
            "agentId": self._record_agent_id(record),
            "agentRegistry": self._record_agent_registry(record),
            "reputationRegistry": self._record_reputation_registry_address(record),
            "claimHash": reputation_trail.get("claim_hash"),
            "claimConfirmed": self._claim_confirmed(record),
            "outcome": {
                "auditStatus": record["status"],
                "challengeStatus": challenge.get("status"),
                "resolution": challenge.get("resolution"),
                "resolutionPath": challenge.get("resolution_path"),
                "resolveTxHash": challenge.get("resolve_tx_hash"),
            },
            "evidence": {
                "proofUri": challenge.get("proof_uri"),
                "evidenceHash": challenge.get("evidence_hash"),
                "verificationStatus": challenge.get("verification_status"),
                "verificationSummary": challenge.get("verification_summary"),
            },
        }

    def _claim_confirmed(self, record: dict[str, Any]) -> bool | None:
        challenge = record.get("challenge")
        if not isinstance(challenge, dict):
            return None
        resolution = str(challenge.get("resolution") or "")
        if resolution == "rejected":
            return True
        if resolution == "upheld":
            return False
        return None

    def _build_validation_seed(self, record: dict[str, Any]) -> dict[str, Any] | None:
        agent_id = self._record_agent_id(record)
        if (
            not self._record_validation_registry_address(record)
            or agent_id is None
            or not self.contract_config.validator_address
        ):
            return None
        request_document = self._build_validation_request_document(record)
        return {
            "status": "pending_request",
            "registry_address": self._record_validation_registry_address(record),
            "source": self._record_validation_source(record) or "configured",
            "agent_id": agent_id,
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

    def _build_committed_evidence_hash(
        self,
        *,
        proof_uri: str,
        evidence_type: str,
        execution_env: str | None,
        evidence_manifest: dict[str, Any] | None,
        chain_id: int,
    ) -> str:
        if evidence_type != "executable_test":
            return "0x" + sha256(proof_uri.encode("utf-8")).hexdigest()
        try:
            with self.evidence_resolver.resolve(
                EvidenceContext(
                    proof_uri=proof_uri,
                    benchmark_id=None,
                    target_contract="",
                    published_report={},
                    evidence_type=evidence_type,
                    execution_env=execution_env,
                    evidence_manifest=deepcopy(evidence_manifest),
                    chain_id=chain_id,
                    rpc_url=self.contract_config.rpc_url,
                )
            ) as resolved:
                return resolved.canonical_hash
        except EvidenceResolutionError as exc:
            raise ValueError(
                f"Executable evidence could not be committed on-chain: {exc}"
            ) from exc

    def _build_validation_request_document(
        self, record: dict[str, Any]
    ) -> dict[str, Any]:
        onchain = record.get("onchain") or {}
        report = record["report"]
        service = self._record_auditor_service(record)
        return {
            "type": "https://eips.ethereum.org/EIPS/eip-8004#validation-request-v1",
            "requestType": "proof-of-audit.audit-claim",
            "auditRecordId": record["id"],
            "agentId": self._record_agent_id(record),
            "agentRegistry": self._record_agent_registry(record),
            "validationRegistry": self._record_validation_registry_address(record),
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
                "registrationUri": service.get("registration_uri"),
                "registrationEndpoint": (
                    f"{self.contract_config.runtime_api_base_url}"
                    f"{service.get('registration_endpoint') or '/auditor/registration'}"
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
            "agentId": self._record_agent_id(record),
            "requestHash": validation["request_hash"],
            "validationRegistry": self._record_validation_registry_address(record),
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
                "evidenceHash": challenge.get("evidence_hash"),
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
        payload["evidence_type"] = str(
            payload.get("evidence_type") or "deterministic_fixture"
        )
        execution_env = payload.get("execution_env")
        payload["execution_env"] = str(execution_env) if execution_env is not None else None
        evidence_manifest = payload.get("evidence_manifest")
        payload["evidence_manifest"] = (
            deepcopy(evidence_manifest) if isinstance(evidence_manifest, dict) else None
        )
        advisory_verdict = payload.get("advisory_verdict")
        payload["advisory_verdict"] = (
            str(advisory_verdict) if advisory_verdict is not None else None
        )
        execution_log = payload.get("execution_log")
        payload["execution_log"] = str(execution_log) if execution_log else None
        matched_findings = payload.get("matched_findings")
        payload["matched_findings"] = (
            [str(item) for item in matched_findings]
            if isinstance(matched_findings, list)
            else []
        )
        unmatched_findings = payload.get("unmatched_findings")
        payload["unmatched_findings"] = (
            [str(item) for item in unmatched_findings]
            if isinstance(unmatched_findings, list)
            else []
        )
        payload["verification_dossier"] = self._normalize_verification_dossier(
            payload.get("verification_dossier"),
            challenge=payload,
        )
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

    def _normalize_agent(
        self, agent: Any, *, default_agent: dict[str, object] | None = None
    ) -> dict[str, object]:
        payload = agent if isinstance(agent, dict) else {}
        defaults = default_agent or self.contract_config.auditor.to_dict()
        normalized = dict(defaults)
        for key, value in payload.items():
            if key == "capabilities" and isinstance(value, list):
                normalized[key] = [str(item) for item in value]
            elif value is not None:
                normalized[key] = value
        return normalized

    def _normalize_auditor_service(
        self, payload: Any, *, service_id: str | None = None
    ) -> dict[str, object]:
        stored = deepcopy(payload) if isinstance(payload, dict) else {}
        selected_service_id = str(
            service_id
            or stored.get("service_id")
            or self.contract_config.auditor_service.service_id
        ).strip()
        configured = self.contract_config.auditor_service_by_id(selected_service_id)
        defaults = (
            configured.to_dict()
            if configured is not None
            else self.contract_config.auditor_service.to_dict()
        )
        normalized = dict(defaults)
        for key, value in stored.items():
            if key in {"submission_modes", "resolution_modes", "supported_trust"} and isinstance(
                value, list
            ):
                normalized[key] = [str(item) for item in value]
            elif value is not None:
                normalized[key] = value
        normalized["service_id"] = selected_service_id or defaults["service_id"]
        return normalized

    def _worker_submission_payload(self, submission: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in submission.items()
            if key
            in {
                "input_kind",
                "chain_id",
                "contract_address",
                "fixture_id",
                "entry_contract",
                "source_bundle_uri",
                "source_bundle_label",
                "repository_url",
            }
        }

    def _require_submission_service(self, service_id: str | None, input_kind: str) -> Any:
        selected_service_id = str(
            service_id or self.contract_config.auditor_service.service_id
        ).strip()
        service = self.contract_config.auditor_service_by_id(selected_service_id)
        if service is None:
            raise ValueError(f"unknown auditor service: {selected_service_id}")
        if not service.active:
            raise ValueError(f"auditor service is inactive: {selected_service_id}")
        if input_kind not in service.submission_modes:
            raise ValueError(
                f"auditor service {selected_service_id} does not support submission mode {input_kind}"
            )
        if service.execution_mode != "local_worker":
            raise ValueError(
                f"auditor service {selected_service_id} uses unsupported execution mode {service.execution_mode}"
            )
        return service

    def _auditor_profile_payload_for_service(self, service_id: str) -> dict[str, object]:
        profile = self.contract_config.auditor_profile_by_service_id(service_id)
        if profile is None:
            raise ValueError(f"unknown auditor service: {service_id}")
        return profile.to_dict()

    def _record_agent_profile(self, record: dict[str, Any]) -> dict[str, Any]:
        agent = record.get("agent")
        if isinstance(agent, dict):
            return agent
        service = self._record_auditor_service(record)
        return self._auditor_profile_payload_for_service(
            str(service.get("service_id") or self.contract_config.auditor_service.service_id)
        )

    def _record_auditor_service(self, record: dict[str, Any]) -> dict[str, Any]:
        service = record.get("auditor_service")
        if isinstance(service, dict):
            return service
        submission = record.get("submission") if isinstance(record.get("submission"), dict) else {}
        return self._normalize_auditor_service(
            {},
            service_id=str(
                submission.get("service_id")
                or self.contract_config.auditor_service.service_id
            ),
        )

    def _record_agent_id(self, record: dict[str, Any]) -> int | None:
        service = self._record_auditor_service(record)
        agent_id = service.get("agent_id")
        return int(agent_id) if isinstance(agent_id, int) else self.contract_config.auditor_agent_id

    def _record_agent_registry(self, record: dict[str, Any]) -> str | None:
        service = self._record_auditor_service(record)
        agent_registry = service.get("agent_registry")
        if isinstance(agent_registry, str) and agent_registry.strip():
            return agent_registry
        return self.contract_config.auditor_agent_registry

    def _record_validation_registry_address(self, record: dict[str, Any]) -> str | None:
        service = self._record_auditor_service(record)
        value = service.get("validation_registry_address")
        if isinstance(value, str) and value.strip():
            return value
        return self.contract_config.validation_registry_address

    def _record_validation_source(self, record: dict[str, Any]) -> str | None:
        service = self._record_auditor_service(record)
        value = service.get("validation_source")
        if isinstance(value, str) and value.strip():
            return value
        return self.contract_config.validation_bridge_source

    def _record_reputation_registry_address(self, record: dict[str, Any]) -> str | None:
        service = self._record_auditor_service(record)
        value = service.get("reputation_registry_address")
        if isinstance(value, str) and value.strip():
            return value
        return self.contract_config.reputation_registry_address

    def _record_reputation_source(self, record: dict[str, Any]) -> str | None:
        service = self._record_auditor_service(record)
        value = service.get("reputation_source")
        if isinstance(value, str) and value.strip():
            return value
        return self.contract_config.reputation_bridge_source

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
        payload["normalized_findings"] = [
            self._normalize_finding_record(finding) for finding in normalized_findings
        ]
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

    def _normalize_finding_record(self, finding: dict[str, Any]) -> dict[str, Any]:
        affected_function = str(finding.get("affected_function") or "").strip()
        affected_surface = affected_function.split("(", 1)[0] if affected_function else ""
        category = str(finding.get("category") or "general").lower()
        detector = str(finding.get("detector") or "deterministic.legacy")
        vulnerability_classes = [category]
        detector_family = detector.split(".")[-1].lower()
        if detector_family and detector_family not in vulnerability_classes:
            vulnerability_classes.append(detector_family)

        preconditions: list[str] = []
        if category == "reentrancy":
            preconditions.append("attacker can trigger a re-entrant control flow")
        elif category == "access_control":
            preconditions.append("attacker can call the affected surface without authorization")
        elif category == "unchecked_external_call":
            preconditions.append("the affected low-level external call can fail")

        evidence_refs: list[str] = []
        evidence_uri = finding.get("evidence_uri")
        if isinstance(evidence_uri, str) and evidence_uri.strip():
            evidence_refs.append(evidence_uri.strip())

        keywords = sorted(
            self._tokenize_finding_text(
                [
                    str(finding.get("title") or ""),
                    str(finding.get("description") or ""),
                    category,
                    detector_family,
                    affected_surface,
                ]
            )
        )

        return {
            "schema_version": "normalized-audit-finding/v1",
            "finding_id": str(finding.get("finding_id") or "finding"),
            "vulnerability_classes": vulnerability_classes,
            "affected_surfaces": [affected_surface] if affected_surface else [],
            "detector_families": [detector_family] if detector_family else [],
            "severity": str(finding.get("severity") or "info").lower(),
            "impact_summary": str(finding.get("impact") or ""),
            "preconditions": preconditions,
            "evidence_refs": evidence_refs,
            "keywords": keywords,
        }

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

    def _tokenize_finding_text(self, parts: list[str]) -> set[str]:
        tokens: set[str] = set()
        for part in parts:
            normalized = re.sub(r"[^a-z0-9]+", " ", part.lower())
            compact = normalized.replace(" ", "")
            for token in normalized.split():
                if len(token) >= 4:
                    tokens.add(token)
            if compact:
                tokens.add(compact)
        return tokens

    def _verification_dossier_payload(
        self,
        *,
        verification_result: Any,
        challenge_defaults: dict[str, Any],
    ) -> dict[str, Any]:
        dossier = getattr(verification_result, "verification_dossier", None)
        if dossier is not None and hasattr(dossier, "to_payload"):
            return self._normalize_verification_dossier(
                dossier.to_payload(),
                challenge=challenge_defaults,
            )

        claim = getattr(verification_result, "challenge_claim", None)
        claim_payload = claim.to_payload() if claim is not None and hasattr(claim, "to_payload") else None

        advisory_verdict = challenge_defaults.get("advisory_verdict")
        recommended_resolution = (
            str(advisory_verdict)
            if isinstance(advisory_verdict, str) and advisory_verdict
            else (
                "manual_review_required"
                if str(challenge_defaults.get("verification_status") or "") != "verified"
                else None
            )
        )
        return self._normalize_verification_dossier(
            {
                "schema_version": "challenge-verifier-dossier/v1",
                "verifier_version": str(challenge_defaults.get("verifier") or ""),
                "evidence_type": str(
                    challenge_defaults.get("evidence_type") or "deterministic_fixture"
                ),
                "integrity": {
                    "status": (
                        "invalid"
                        if str(challenge_defaults.get("verification_status") or "")
                        == "invalid_evidence"
                        else "valid"
                    ),
                    "committed_evidence_hash": challenge_defaults.get("evidence_hash"),
                },
                "execution": {
                    "status": (
                        "not_executed"
                        if challenge_defaults.get("evidence_type") == "deterministic_fixture"
                        else "unknown"
                    ),
                    "execution_env": challenge_defaults.get("execution_env"),
                },
                "claim": claim_payload,
                "comparison": {
                    "status": (
                        "already_covered"
                        if advisory_verdict == "rejected"
                        else (
                            "likely_new_issue"
                            if advisory_verdict == "upheld"
                            else "not_assessed"
                        )
                    ),
                    "confidence": "unknown",
                    "rationale": None,
                    "matched_finding_ids": challenge_defaults.get("matched_findings") or [],
                    "matched_findings": [
                        {
                            "finding_id": str(item),
                            "relationship": (
                                "already_covered"
                                if advisory_verdict == "rejected"
                                else "supporting_context"
                            ),
                            "confidence": "unknown",
                            "rationale": None,
                            "score": None,
                        }
                        for item in (challenge_defaults.get("matched_findings") or [])
                    ],
                    "unmatched_signals": challenge_defaults.get("unmatched_findings") or [],
                    "disagreement_status": "not_checked",
                    "disagreement_detail": None,
                },
                "policy": {
                    "status": (
                        "rejected"
                        if advisory_verdict == "rejected"
                        else "manual_review_required"
                    ),
                    "advisory_only": bool(
                        getattr(verification_result, "advisory_only", False)
                    ),
                    "recommended_resolution": recommended_resolution,
                    "abstained": advisory_verdict is None,
                    "confidence": "unknown",
                    "rationale": None,
                },
                "model_metadata": {},
            },
            challenge=challenge_defaults,
        )

    def _normalize_verification_dossier(
        self,
        dossier: Any,
        *,
        challenge: dict[str, Any],
    ) -> dict[str, Any]:
        payload = deepcopy(dossier) if isinstance(dossier, dict) else {}
        payload["schema_version"] = str(
            payload.get("schema_version") or "challenge-verifier-dossier/v1"
        )
        payload["verifier_version"] = str(
            payload.get("verifier_version") or challenge.get("verifier") or "unknown-verifier"
        )
        payload["evidence_type"] = str(
            payload.get("evidence_type")
            or challenge.get("evidence_type")
            or "deterministic_fixture"
        )

        integrity = payload.get("integrity")
        if not isinstance(integrity, dict):
            integrity = {}
        payload["integrity"] = {
            "status": str(integrity.get("status") or "unknown"),
            "committed_evidence_hash": (
                str(integrity.get("committed_evidence_hash"))
                if integrity.get("committed_evidence_hash") is not None
                else challenge.get("evidence_hash")
            ),
        }

        execution = payload.get("execution")
        if not isinstance(execution, dict):
            execution = {}
        payload["execution"] = {
            "status": str(execution.get("status") or "unknown"),
            "execution_env": (
                str(execution.get("execution_env"))
                if execution.get("execution_env") is not None
                else (
                    str(challenge.get("execution_env"))
                    if challenge.get("execution_env") is not None
                    else None
                )
            ),
            "backend": (
                str(execution.get("backend"))
                if execution.get("backend") is not None
                else None
            ),
            "isolation_level": (
                str(execution.get("isolation_level"))
                if execution.get("isolation_level") is not None
                else None
            ),
            "source_path": (
                str(execution.get("source_path"))
                if execution.get("source_path") is not None
                else None
            ),
            "fork_block_number": (
                int(execution.get("fork_block_number"))
                if execution.get("fork_block_number") is not None
                else None
            ),
        }

        claim = payload.get("claim")
        payload["claim"] = self._normalize_challenge_claim(claim)

        comparison = payload.get("comparison")
        if not isinstance(comparison, dict):
            comparison = {}
        payload["comparison"] = {
            "status": str(comparison.get("status") or "unknown"),
            "confidence": str(comparison.get("confidence") or "unknown"),
            "rationale": (
                str(comparison.get("rationale"))
                if comparison.get("rationale") is not None
                else None
            ),
            "matched_finding_ids": [
                str(item)
                for item in (
                    comparison.get("matched_finding_ids")
                    if isinstance(comparison.get("matched_finding_ids"), list)
                    else challenge.get("matched_findings") or []
                )
            ],
            "matched_findings": [
                {
                    "finding_id": str(item.get("finding_id") or "finding"),
                    "relationship": str(item.get("relationship") or "unknown"),
                    "confidence": str(item.get("confidence") or "unknown"),
                    "rationale": (
                        str(item.get("rationale"))
                        if item.get("rationale") is not None
                        else None
                    ),
                    "score": (
                        float(item.get("score"))
                        if item.get("score") is not None
                        else None
                    ),
                }
                for item in (
                    comparison.get("matched_findings")
                    if isinstance(comparison.get("matched_findings"), list)
                    else []
                )
                if isinstance(item, dict)
            ],
            "unmatched_signals": [
                str(item)
                for item in (
                    comparison.get("unmatched_signals")
                    if isinstance(comparison.get("unmatched_signals"), list)
                    else challenge.get("unmatched_findings") or []
                )
            ],
            "disagreement_status": str(
                comparison.get("disagreement_status") or "not_checked"
            ),
            "disagreement_detail": (
                str(comparison.get("disagreement_detail"))
                if comparison.get("disagreement_detail") is not None
                else None
            ),
        }

        policy = payload.get("policy")
        if not isinstance(policy, dict):
            policy = {}
        advisory_verdict = challenge.get("advisory_verdict")
        payload["policy"] = {
            "status": str(
                policy.get("status")
                or advisory_verdict
                or "manual_review_required"
            ),
            "advisory_only": bool(policy.get("advisory_only", False)),
            "recommended_resolution": (
                str(policy.get("recommended_resolution"))
                if policy.get("recommended_resolution") is not None
                else (
                    str(advisory_verdict)
                    if advisory_verdict is not None
                    else "manual_review_required"
                )
            ),
            "abstained": bool(policy.get("abstained", advisory_verdict is None)),
            "confidence": str(policy.get("confidence") or "unknown"),
            "rationale": (
                str(policy.get("rationale"))
                if policy.get("rationale") is not None
                else None
            ),
        }
        model_metadata = payload.get("model_metadata")
        payload["model_metadata"] = (
            deepcopy(model_metadata) if isinstance(model_metadata, dict) else {}
        )
        return payload

    def _normalize_challenge_claim(self, claim: Any) -> dict[str, Any] | None:
        if claim is None:
            return None
        payload = deepcopy(claim) if isinstance(claim, dict) else {}
        if not payload:
            return None
        return {
            "schema_version": str(payload.get("schema_version") or "challenge-claim/v1"),
            "claim_type": str(payload.get("claim_type") or "generic_claim"),
            "basis": str(payload.get("basis") or "unknown"),
            "confidence": str(payload.get("confidence") or "unknown"),
            "affected_surfaces": [
                str(item)
                for item in payload.get("affected_surfaces", [])
                if isinstance(item, str) and item
            ],
            "preconditions": [
                str(item)
                for item in payload.get("preconditions", [])
                if isinstance(item, str) and item
            ],
            "demonstrated_effect": (
                str(payload.get("demonstrated_effect"))
                if payload.get("demonstrated_effect") is not None
                else None
            ),
            "claimed_impact": (
                str(payload.get("claimed_impact"))
                if payload.get("claimed_impact") is not None
                else None
            ),
            "supporting_signals": [
                str(item)
                for item in payload.get("supporting_signals", [])
                if isinstance(item, str) and item
            ],
        }

    def _normalize_submission(self, submission: dict[str, Any]) -> dict[str, Any]:
        input_kind = submission.get("input_kind", "deployed_address")
        service_id = str(
            submission.get("service_id") or self.contract_config.auditor_service.service_id
        ).strip()
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
                "service_id": service_id,
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
                "service_id": service_id,
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
                "service_id": service_id,
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
            "service_id": service_id,
            "chain_id": chain_id or self.contract_config.chain_id,
            "contract_address": contract_address.lower(),
            "fixture_id": fixture_id,
            "entry_contract": entry_contract,
            "source_bundle_uri": source_bundle_uri,
            "source_bundle_label": source_bundle_label,
            "repository_url": repository_url,
        }

    def _normalize_target_key(self, contract_address: str | None) -> str:
        if not contract_address:
            raise ValueError("contract_address is required to derive a target key")
        return str(contract_address).strip().lower()

    def _target_auditor_key(self, target_key: str, auditor_id: str) -> str:
        return f"{target_key}::{auditor_id.strip()}"
