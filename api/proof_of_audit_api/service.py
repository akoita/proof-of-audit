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
    ProofOfAuditPublisher,
)
from proof_of_audit_agent.worker import AuditWorker
from proof_of_audit_api.store import JsonStore


class AuditService:
    def __init__(
        self,
        data_root: Path,
        contract_config: ContractConfig | None = None,
        publisher: ProofOfAuditPublisher | None = None,
    ) -> None:
        self.store = JsonStore(data_root)
        self.contract_config = contract_config or ContractConfig.from_env()
        self.worker = AuditWorker(self.contract_config.demo_fixtures_file)
        self.publisher = publisher or ProofOfAuditPublisher.from_config_if_ready(
            self.contract_config
        )

    def create_audit(
        self, contract_address: str, submitted_by: str = "anonymous"
    ) -> dict[str, Any]:
        report = self.worker.run_audit(contract_address)
        audit_id = str(uuid4())
        record = {
            "id": audit_id,
            "contract_address": contract_address.lower(),
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
        if record["status"] != "published" or record["onchain"] is None:
            raise ValueError("audit must be published before challenge")
        tx_hash = (
            "0x"
            + sha256(f"challenge:{audit_id}:{proof_uri}".encode("utf-8")).hexdigest()
        )
        record["challenge"] = {
            "challenger": challenger,
            "proof_uri": proof_uri,
            "submitted_at": datetime.now(UTC).isoformat(),
            "verifier": "deterministic-demo-verifier",
            "status": "accepted" if "poc" in proof_uri.lower() else "pending-review",
            "challenge_tx_hash": tx_hash,
            "challenge_tx_url": self.contract_config.transaction_url(tx_hash),
        }
        record["status"] = "challenged"
        self.store.write(audit_id, record)
        return record

    def _require_audit(self, audit_id: str) -> dict[str, Any]:
        record = self.get_audit(audit_id)
        if record is None:
            raise KeyError(audit_id)
        return record
