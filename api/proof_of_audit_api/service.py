from __future__ import annotations

from datetime import datetime, UTC
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

from proof_of_audit_api.config import ContractConfig
from proof_of_audit_api.publisher import (
    OnchainConfigurationError,
    OnchainPublishError,
    OnchainResolveError,
    ProofOfAuditPublisher,
)
from proof_of_audit_agent.challenge_verifier import DeterministicChallengeVerifier
from proof_of_audit_agent.worker import AuditWorker
from proof_of_audit_api.store import JsonStore


class AuditService:
    def __init__(
        self,
        data_root: Path,
        contract_config: ContractConfig | None = None,
        publisher: ProofOfAuditPublisher | None = None,
        arbiter_client: ProofOfAuditPublisher | None = None,
    ) -> None:
        self.store = JsonStore(data_root)
        self.contract_config = contract_config or ContractConfig.from_env()
        self.worker = AuditWorker(self.contract_config.demo_fixtures_file)
        self.challenge_verifier = DeterministicChallengeVerifier()
        self.publisher = publisher or ProofOfAuditPublisher.from_config_if_ready(
            self.contract_config
        )
        self.arbiter_client = arbiter_client or ProofOfAuditPublisher.from_config_if_ready(
            self.contract_config,
            private_key=self.contract_config.arbiter_private_key,
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
        report = self.worker.run_submission(**normalized_submission)
        audit_id = str(uuid4())
        record = {
            "id": audit_id,
            "contract_address": normalized_submission["contract_address"],
            "submission": normalized_submission,
            "submitted_by": submitted_by,
            "status": "draft",
            "created_at": datetime.now(UTC).isoformat(),
            "report": report.to_dict(),
            "onchain": None,
            "challenge": None,
        }
        self.store.write(audit_id, record)
        return record

    def get_audit(self, audit_id: str) -> dict[str, Any] | None:
        return self.store.read(audit_id)

    def list_audits(self) -> list[dict[str, Any]]:
        records = self.store.list_all()
        return sorted(records, key=lambda record: record["created_at"], reverse=True)

    def list_demo_fixtures(self) -> list[dict[str, Any]]:
        return self.worker.list_demo_fixtures()

    def publish_audit(
        self, audit_id: str, stake_wei: int, agent_identity: str
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
        self.store.write(audit_id, record)
        return record

    def _require_audit(self, audit_id: str) -> dict[str, Any]:
        record = self.get_audit(audit_id)
        if record is None:
            raise KeyError(audit_id)
        return record

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
