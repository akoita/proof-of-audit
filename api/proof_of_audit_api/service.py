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
    OnchainRequestError,
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
    VERIFIER_NAME as PROOF_URI_VERIFIER_NAME,
)
from proof_of_audit_agent.executable_evidence_verifier import (
    ExecutableEvidenceVerifier,
    VERIFIER_NAME as EXECUTABLE_VERIFIER_NAME,
)
from proof_of_audit_agent.executable_evidence_resolver import (
    EvidenceResolutionError,
    ExecutableEvidenceResolver,
)
from proof_of_audit_agent.deterministic_auditor_backend import (
    LEGACY_BENCHMARK_ADDRESSES,
)
from proof_of_audit_agent.runtime import WorkerRuntimeConfig
from proof_of_audit_agent.worker import AuditWorker
from proof_of_audit_api.store import AuditStore, CloudSqlPostgresConfig, create_store
from web3 import HTTPProvider, Web3


def _network_is_local(network: str | None) -> bool:
    normalized = str(network or "").strip().lower()
    return (
        "anvil" in normalized
        or "localhost" in normalized
        or "eth-tester" in normalized
        or normalized == "eth_tester"
        or normalized == "tester"
        or normalized == "local"
    )


_CHALLENGER_EVENT_PRIORITY = {
    "challenge_resolved": 3,
    "challenge_opened": 2,
    "audit_published": 1,
}

_SEVERITY_RANKING = {
    "info": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}

_DEFAULT_CHALLENGE_POLICY = {
    "policy_version": "challenge-policy/v1",
    "allowed_evidence_types": ["deterministic_fixture", "executable_test"],
    "min_severity_threshold": "info",
    "allow_informational_only": True,
    "requires_material_incorrectness": False,
    "admissibility_mode": "broad",
}

_POLICY_OPENNESS_THRESHOLD_POINTS = {
    "info": 30,
    "low": 24,
    "medium": 18,
    "high": 10,
    "critical": 4,
}

_EIP1967_IMPLEMENTATION_SLOT = int(
    "360894A13BA1A3210667C828492DB98DCA3E2076CC3735A920A3CA505D382BBC",
    16,
)
_EIP1967_BEACON_SLOT = int(
    "A3F0AD74E5423AEBFD80D3EF4346578335A9A72AEAEE59FF6CB3582B35133D50",
    16,
)


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
        postgres_config: CloudSqlPostgresConfig | None = None,
    ) -> None:
        self.data_root = data_root
        self._last_created_at: datetime | None = None
        self._chain_web3: Web3 | None = None
        self.store = store or create_store(
            root=data_root,
            kind=store_kind,
            database_path=store_path,
            postgres_config=postgres_config,
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
                agent_forge_service_url=self.contract_config.agent_forge_service_url,
                agent_forge_service_token=self.contract_config.agent_forge_service_token,
                agent_forge_service_profile_id=self.contract_config.agent_forge_service_profile_id,
                agent_forge_service_report_schema=self.contract_config.agent_forge_service_report_schema,
                agent_forge_service_poll_interval_seconds=self.contract_config.agent_forge_service_poll_interval_seconds,
                agent_forge_service_poll_timeout_seconds=self.contract_config.agent_forge_service_poll_timeout_seconds,
                agent_forge_service_request_timeout_seconds=self.contract_config.agent_forge_service_request_timeout_seconds,
                source_bundle_storage_kind=self.contract_config.source_bundle_storage_kind,
                source_bundle_gcs_bucket=self.contract_config.source_bundle_gcs_bucket,
                source_bundle_gcs_prefix=self.contract_config.source_bundle_gcs_prefix,
                source_bundle_ipfs_api_url=self.contract_config.source_bundle_ipfs_api_url,
                source_bundle_ipfs_auth_header=self.contract_config.source_bundle_ipfs_auth_header,
                sourcify_base_url=self.contract_config.sourcify_base_url,
                explorer_api_url=self.contract_config.explorer_api_url,
                explorer_api_key=self.contract_config.explorer_api_key,
                allow_deployed_address_deterministic_fallback=_network_is_local(
                    self.contract_config.network
                ),
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

    def close(self) -> None:
        self.store.close()

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
        snapshot_metadata = self._capture_deployed_address_snapshot(normalized_submission)
        if snapshot_metadata["snapshot_block_number"] is not None:
            normalized_submission.update(snapshot_metadata)
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
        self._validate_live_deployed_address_execution(
            normalized_submission=normalized_submission,
            execution_result=execution_result,
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
            "created_at": self._next_created_at_isoformat(),
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

    def _chain_web3_client(self) -> Web3 | None:
        for client in (
            self.publisher,
            self.arbiter_client,
            self.validation_bridge,
            self.reputation_bridge,
        ):
            web3 = getattr(client, "web3", None)
            if isinstance(web3, Web3):
                return web3
        if not self.contract_config.rpc_url:
            return None
        if self._chain_web3 is None:
            self._chain_web3 = Web3(HTTPProvider(self.contract_config.rpc_url))
        return self._chain_web3

    def _capture_deployed_address_snapshot(
        self, submission: dict[str, Any]
    ) -> dict[str, Any]:
        empty_snapshot = {
            "snapshot_block_number": None,
            "snapshot_block_hash": None,
            "target_code_hash_at_snapshot": None,
            "proxy_kind": None,
            "proxy_resolution_status": None,
            "proxy_resolution_detail": None,
            "implementation_address_at_snapshot": None,
            "implementation_code_hash_at_snapshot": None,
        }
        if submission.get("input_kind") != "deployed_address":
            return empty_snapshot
        web3 = self._chain_web3_client()
        if web3 is None:
            return empty_snapshot
        contract_address = submission.get("contract_address")
        if not isinstance(contract_address, str) or not contract_address.strip():
            return empty_snapshot
        latest_block = web3.eth.get_block("latest")
        block_number = int(latest_block["number"])
        block_identifier: Any = "latest"
        code = bytes(
            web3.eth.get_code(
                Web3.to_checksum_address(contract_address),
                block_identifier=block_identifier,
            )
        )
        snapshot = {
            "snapshot_block_number": block_number,
            "snapshot_block_hash": Web3.to_hex(latest_block["hash"]),
            "target_code_hash_at_snapshot": Web3.to_hex(Web3.keccak(code)),
            **self._resolve_proxy_identity_snapshot(
                web3=web3,
                target_address=contract_address,
                block_identifier=block_identifier,
            ),
        }
        return snapshot

    def _resolve_proxy_identity_snapshot(
        self,
        *,
        web3: Web3,
        target_address: str,
        block_identifier: Any,
    ) -> dict[str, Any]:
        target = Web3.to_checksum_address(target_address)
        implementation_address = self._storage_word_to_address(
            web3.eth.get_storage_at(
                target,
                _EIP1967_IMPLEMENTATION_SLOT,
                block_identifier=block_identifier,
            )
        )
        if implementation_address is not None:
            implementation_code_hash = self._code_hash_at_snapshot(
                web3=web3,
                contract_address=implementation_address,
                block_identifier=block_identifier,
            )
            if implementation_code_hash is None:
                return {
                    "proxy_kind": "eip1967",
                    "proxy_resolution_status": "ambiguous_proxy_identity",
                    "proxy_resolution_detail": (
                        "Detected an EIP-1967 implementation slot, but the resolved "
                        "implementation had no code at the snapshot block."
                    ),
                    "implementation_address_at_snapshot": implementation_address,
                    "implementation_code_hash_at_snapshot": None,
                }
            return {
                "proxy_kind": "eip1967",
                "proxy_resolution_status": "resolved",
                "proxy_resolution_detail": (
                    "Resolved implementation identity from the EIP-1967 implementation slot."
                ),
                "implementation_address_at_snapshot": implementation_address,
                "implementation_code_hash_at_snapshot": implementation_code_hash,
            }

        beacon_address = self._storage_word_to_address(
            web3.eth.get_storage_at(
                target,
                _EIP1967_BEACON_SLOT,
                block_identifier=block_identifier,
            )
        )
        if beacon_address is not None:
            return {
                "proxy_kind": "eip1967-beacon",
                "proxy_resolution_status": "unsupported_proxy_topology",
                "proxy_resolution_detail": (
                    "Detected an EIP-1967 beacon proxy, but beacon-backed implementation "
                    "resolution is not supported in v1."
                ),
                "implementation_address_at_snapshot": None,
                "implementation_code_hash_at_snapshot": None,
            }

        return {
            "proxy_kind": None,
            "proxy_resolution_status": "direct_target",
            "proxy_resolution_detail": (
                "No supported proxy indirection was detected at the snapshot block."
            ),
            "implementation_address_at_snapshot": None,
            "implementation_code_hash_at_snapshot": None,
        }

    def _storage_word_to_address(self, value: Any) -> str | None:
        if not isinstance(value, (bytes, bytearray)):
            return None
        raw = bytes(value)
        if not raw:
            return None
        if len(raw) < 20:
            raw = (b"\x00" * (20 - len(raw))) + raw
        address_bytes = raw[-20:]
        if int.from_bytes(address_bytes, "big") == 0:
            return None
        return Web3.to_checksum_address("0x" + address_bytes.hex())

    def _code_hash_at_snapshot(
        self,
        *,
        web3: Web3,
        contract_address: str,
        block_identifier: Any,
    ) -> str | None:
        code = bytes(
            web3.eth.get_code(
                Web3.to_checksum_address(contract_address),
                block_identifier=block_identifier,
            )
        )
        if len(code) == 0:
            return None
        return Web3.to_hex(Web3.keccak(code))

    def _record_snapshot_metadata(self, record: dict[str, Any]) -> dict[str, Any]:
        submission = record.get("submission") if isinstance(record.get("submission"), dict) else {}
        return {
            "snapshot_block_number": (
                int(submission["snapshot_block_number"])
                if submission.get("snapshot_block_number") is not None
                else None
            ),
            "snapshot_block_hash": (
                str(submission["snapshot_block_hash"])
                if submission.get("snapshot_block_hash") is not None
                else None
            ),
            "target_code_hash_at_snapshot": (
                str(submission["target_code_hash_at_snapshot"])
                if submission.get("target_code_hash_at_snapshot") is not None
                else None
            ),
            "proxy_kind": (
                str(submission["proxy_kind"])
                if submission.get("proxy_kind") is not None
                else None
            ),
            "proxy_resolution_status": (
                str(submission["proxy_resolution_status"])
                if submission.get("proxy_resolution_status") is not None
                else None
            ),
            "proxy_resolution_detail": (
                str(submission["proxy_resolution_detail"])
                if submission.get("proxy_resolution_detail") is not None
                else None
            ),
            "implementation_address_at_snapshot": (
                str(submission["implementation_address_at_snapshot"])
                if submission.get("implementation_address_at_snapshot") is not None
                else None
            ),
            "implementation_code_hash_at_snapshot": (
                str(submission["implementation_code_hash_at_snapshot"])
                if submission.get("implementation_code_hash_at_snapshot") is not None
                else None
            ),
        }

    def _assert_snapshot_publishable(self, record: dict[str, Any]) -> None:
        submission = record.get("submission") if isinstance(record.get("submission"), dict) else {}
        if submission.get("input_kind") != "deployed_address":
            return
        snapshot = self._record_snapshot_metadata(record)
        if snapshot["target_code_hash_at_snapshot"] is None:
            return
        current_snapshot = self._capture_deployed_address_snapshot(submission)
        current_hash = current_snapshot["target_code_hash_at_snapshot"]
        if (
            current_hash is not None
            and current_hash != snapshot["target_code_hash_at_snapshot"]
        ):
            raise ValueError(
                "target code changed since audit start; create a new audit before publish"
            )
        if (
            snapshot["implementation_address_at_snapshot"] is not None
            or snapshot["implementation_code_hash_at_snapshot"] is not None
        ):
            current_implementation_address = current_snapshot[
                "implementation_address_at_snapshot"
            ]
            current_implementation_hash = current_snapshot[
                "implementation_code_hash_at_snapshot"
            ]
            if (
                current_implementation_address
                != snapshot["implementation_address_at_snapshot"]
                or current_implementation_hash
                != snapshot["implementation_code_hash_at_snapshot"]
            ):
                raise ValueError(
                    "proxy implementation changed since audit start; create a new audit before publish"
                )

    def _validate_live_deployed_address_execution(
        self,
        *,
        normalized_submission: dict[str, Any],
        execution_result: Any,
    ) -> None:
        if normalized_submission.get("input_kind") != "deployed_address":
            return

        contract_address = self._normalize_target_key(
            normalized_submission.get("contract_address")
        )
        if self._is_local_network() or contract_address in LEGACY_BENCHMARK_ADDRESSES:
            return

        execution = getattr(execution_result, "execution", None)
        if (
            execution is not None
            and execution.backend == "agent_forge"
            and execution.status == "completed"
            and not execution.fallback_used
        ):
            return

        raise ValueError(
            f"deployed_address submissions on {self.contract_config.network} require live agent-forge analysis; deterministic fallback is disabled for this address"
        )

    def _is_local_network(self) -> bool:
        return _network_is_local(self.contract_config.network)

    def _is_configured_fixture_address(self, contract_address: str) -> bool:
        return any(
            self._normalize_target_key(fixture["address"]) == contract_address
            for fixture in self.worker.list_demo_fixtures()
            if isinstance(fixture, dict) and fixture.get("address")
        )

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

    def create_audit_request(
        self,
        *,
        contract_address: str,
        bounty_wei: int,
        response_window_seconds: int,
        filters: dict[str, Any] | None = None,
        submitted_by: str = "anonymous",
    ) -> dict[str, Any]:
        if self.publisher is None:
            raise OnchainConfigurationError(
                "On-chain audit requests are not configured for this API instance."
            )

        target_contract = self._normalize_target_key(contract_address)
        normalized_filters = self._normalize_marketplace_filters(filters)
        required_identity = self._resolve_request_required_identity(normalized_filters)
        allowlist_snapshot = self._resolve_request_allowlist(
            normalized_filters["allowed_service_ids"],
            enabled=normalized_filters["whitelist_mode"] == "allowlist",
        )
        materialized_filters = deepcopy(normalized_filters)
        if required_identity["agent_registry"] is not None:
            materialized_filters["required_identity_registry"] = required_identity[
                "agent_registry"
            ]
        if required_identity["agent_id"] is not None:
            materialized_filters["required_identity_agent_id"] = required_identity[
                "agent_id"
            ]
        onchain_result = self.publisher.create_audit_request(
            target_address=target_contract,
            bounty_wei=bounty_wei,
            response_window_seconds=response_window_seconds,
            minimum_stake_wei=int(materialized_filters["minimum_stake_wei"]),
            allowlist_enabled=materialized_filters["whitelist_mode"] == "allowlist",
            identity_registry=required_identity["agent_registry"],
            required_agent_id=int(required_identity["agent_id"] or 0),
            allowlisted_auditors=allowlist_snapshot["auditor_addresses"],
        )
        onchain_request = self.publisher.get_audit_request(onchain_result.request_id)
        record = self._normalize_audit_request_record(
            {
                "request_id": str(onchain_result.request_id),
                "status": onchain_request.state,
                "requester": onchain_request.requester_address,
                "input_kind": "deployed_address",
                "contract_address": onchain_request.target_address,
                "chain_id": onchain_result.chain_id,
                "bounty_wei": onchain_request.bounty_wei,
                "protocol_fee_wei": 0,
                "response_window_seconds": response_window_seconds,
                "response_window_end": self._isoformat_unix_timestamp(
                    onchain_request.response_window_end
                ),
                "created_at": self._isoformat_unix_timestamp(onchain_request.created_at),
                "claim_count": onchain_request.claim_count,
                "request_tx_hash": onchain_result.tx_hash,
                "request_tx_url": self.contract_config.transaction_url(
                    onchain_result.tx_hash
                ),
                "filters": materialized_filters,
                "metadata": {
                    "submitted_by": submitted_by,
                    "onchain_eligibility": onchain_request.eligibility,
                    "allowlisted_auditor_addresses": allowlist_snapshot[
                        "auditor_addresses"
                    ],
                    "allowlisted_services": allowlist_snapshot["services"],
                    "required_identity": required_identity,
                },
            }
        )
        self._upsert_audit_request_record(record)
        return self.get_audit_request(record["request_id"]) or record

    def get_audit_request(self, request_id: str) -> dict[str, Any] | None:
        return next(
            (
                item
                for item in self._all_normalized_audit_requests()
                if item["request_id"] == str(request_id).strip()
            ),
            None,
        )

    def submit_audit_request_claim(
        self,
        request_id: str,
        *,
        audit_id: str,
        stake_wei: int,
        challenge_policy: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        request_record = self.get_audit_request(request_id)
        if request_record is None:
            raise KeyError(request_id)
        record = self._require_audit(audit_id)
        if record["status"] != "draft":
            raise ValueError("audit must be in draft status before request claim submission")
        if self.publisher is None:
            raise OnchainConfigurationError(
                "On-chain request claim submission is not configured for this API instance."
            )
        self._assert_snapshot_publishable(record)
        if record["contract_address"] != request_record["contract_address"]:
            raise ValueError("audit target must match the audit request target")

        service = self._record_auditor_service(record)
        agent = self._record_agent_profile(record)
        agent_id = service.get("agent_id")
        agent_registry = service.get("agent_registry")
        if not isinstance(agent_id, int) or not agent_registry:
            raise ValueError(
                "auditor service is missing the canonical on-chain identity required for request claims"
            )

        report = record["report"]
        snapshot = self._record_snapshot_metadata(record)
        claim_result = self.publisher.submit_audit_request_claim(
            request_id=int(request_record["request_id"]),
            agent_registry=str(agent_registry),
            agent_id=int(agent_id),
            report_hash=str(report["report_hash"]),
            metadata_hash=str(report["metadata_hash"]),
            max_severity=int(report["max_severity"]),
            finding_count=int(report["finding_count"]),
            stake_wei=stake_wei,
        )
        onchain_claim = self.publisher.get_audit_request_claim(claim_result.claim_id)
        updated_record = deepcopy(record)
        updated_record["status"] = "published"
        updated_record["onchain"] = {
            "request_id": claim_result.request_id,
            "request_claim_id": claim_result.claim_id,
            "publication_mode": "audit_request_claim",
            "claim_state": onchain_claim.state,
            "claim_tx_hash": claim_result.tx_hash,
            "claim_tx_url": self.contract_config.transaction_url(claim_result.tx_hash),
            "publish_tx_hash": claim_result.tx_hash,
            "publish_tx_url": self.contract_config.transaction_url(claim_result.tx_hash),
            "published_at": self._isoformat_unix_timestamp(onchain_claim.submitted_at),
            "network": self.contract_config.network,
            "chain_id": claim_result.chain_id,
            "contract_address": self.contract_config.contract_address,
            "explorer_base_url": self.contract_config.explorer_base_url,
            "agent_identity": str(agent.get("id") or self.contract_config.auditor.id),
            "agent_name": str(agent.get("name") or self.contract_config.auditor.name),
            "agent_version": str(
                agent.get("version") or self.contract_config.auditor.version
            ),
            "stake_wei": onchain_claim.stake_wei,
            "report_hash": report["report_hash"],
            "metadata_hash": report["metadata_hash"],
            "max_severity": int(report["max_severity"]),
            "finding_count": int(report["finding_count"]),
            "agent_id": onchain_claim.agent_id,
            "agent_registry": onchain_claim.agent_registry.lower(),
            "auditor_address": onchain_claim.auditor_address.lower(),
            "snapshot_block_number": snapshot["snapshot_block_number"],
            "snapshot_block_hash": snapshot["snapshot_block_hash"],
            "target_code_hash_at_snapshot": snapshot["target_code_hash_at_snapshot"],
            "proxy_kind": snapshot["proxy_kind"],
            "proxy_resolution_status": snapshot["proxy_resolution_status"],
            "proxy_resolution_detail": snapshot["proxy_resolution_detail"],
            "implementation_address_at_snapshot": snapshot[
                "implementation_address_at_snapshot"
            ],
            "implementation_code_hash_at_snapshot": snapshot[
                "implementation_code_hash_at_snapshot"
            ],
            "challenge_policy": self._normalize_challenge_policy(challenge_policy),
        }
        self.store.write(audit_id, updated_record)
        return self.get_audit(audit_id) or updated_record

    def list_audit_request_claims(self, request_id: str) -> list[dict[str, Any]]:
        request_record = self.get_audit_request(request_id)
        if request_record is None:
            raise KeyError(request_id)

        items: list[dict[str, Any]] = []
        for record in self._all_normalized_records():
            onchain = record.get("onchain")
            if not isinstance(onchain, dict):
                continue
            if str(onchain.get("request_id") or "") != str(request_record["request_id"]):
                continue
            items.append(self._build_audit_request_claim_payload(record))

        return sorted(
            items,
            key=lambda item: str(item.get("submitted_at") or ""),
            reverse=True,
        )

    def list_audit_requests(self, status: str | None = None) -> list[dict[str, Any]]:
        normalized_status = str(status or "").strip().lower() or None
        items = self._all_normalized_audit_requests()
        if normalized_status is not None:
            items = [
                item
                for item in items
                if str(item.get("status") or "").strip().lower() == normalized_status
            ]
        return items

    def build_audit_request_eligibility(
        self,
        request_id: str,
        auditor_service_id: str,
    ) -> dict[str, Any] | None:
        request_record = next(
            (
                item
                for item in self._all_normalized_audit_requests()
                if item["request_id"] == request_id
            ),
            None,
        )
        if request_record is None:
            return None
        matches = self._build_auditor_matches(request_record["filters"])
        selected_match = next(
            (
                item
                for item in matches
                if item["service_id"] == auditor_service_id.strip()
            ),
            None,
        )
        if selected_match is None:
            return {
                "request_id": request_id,
                "auditor_service_id": auditor_service_id.strip(),
                "eligible": False,
                "approximate": True,
                "minimum_stake_wei": int(
                    request_record["filters"].get("minimum_stake_wei") or 0
                ),
                "reasons": ["Auditor service is not present in the current directory."],
            }
        reasons = self._request_eligibility_reasons(
            request_record=request_record,
            auditor_service=selected_match,
        )
        return {
            "request_id": request_id,
            "auditor_service_id": auditor_service_id.strip(),
            "eligible": len(reasons) == 0,
            "approximate": True,
            "minimum_stake_wei": int(
                request_record["filters"].get("minimum_stake_wei") or 0
            ),
            "reasons": reasons or ["Matches the current preview filters."],
        }

    def _audit_request_catalog_path(self) -> Path:
        return self.data_root / "audit-requests.json"

    def _all_normalized_audit_requests(self) -> list[dict[str, Any]]:
        path = self._audit_request_catalog_path()
        if not path.exists():
            return []
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return []
        items = payload.get("items")
        if not isinstance(items, list):
            return []
        normalized_items = [
            self._normalize_audit_request_record(item)
            for item in items
            if isinstance(item, dict)
        ]
        normalized_items = [
            self._sync_audit_request_record(item) for item in normalized_items
        ]
        return sorted(
            normalized_items,
            key=lambda item: str(item.get("created_at") or ""),
            reverse=True,
        )

    def _normalize_audit_request_record(self, payload: dict[str, Any]) -> dict[str, Any]:
        input_kind = str(payload.get("input_kind") or "deployed_address").strip().lower()
        if input_kind not in {"deployed_address", "source_bundle", "repository_url"}:
            input_kind = "deployed_address"
        return {
            "request_id": str(payload.get("request_id") or payload.get("id") or "").strip(),
            "status": str(payload.get("status") or "open").strip().lower(),
            "requester": (
                self._normalize_target_key(payload.get("requester"))
                if payload.get("requester") is not None
                else None
            ),
            "input_kind": input_kind,
            "contract_address": self._normalize_target_key(payload.get("contract_address")),
            "chain_id": (
                int(payload["chain_id"])
                if payload.get("chain_id") is not None
                else None
            ),
            "entry_contract": (
                str(payload.get("entry_contract")).strip()
                if payload.get("entry_contract") is not None
                else None
            ),
            "bounty_wei": max(int(payload.get("bounty_wei") or 0), 0),
            "protocol_fee_wei": max(int(payload.get("protocol_fee_wei") or 0), 0),
            "response_window_seconds": (
                int(payload["response_window_seconds"])
                if payload.get("response_window_seconds") is not None
                else None
            ),
            "response_window_end": (
                str(payload.get("response_window_end")).strip()
                if payload.get("response_window_end") is not None
                else None
            ),
            "created_at": (
                str(payload.get("created_at")).strip()
                if payload.get("created_at") is not None
                else None
            ),
            "claim_count": max(int(payload.get("claim_count") or 0), 0),
            "request_tx_hash": (
                str(payload.get("request_tx_hash")).strip()
                if payload.get("request_tx_hash") is not None
                else None
            ),
            "request_tx_url": (
                str(payload.get("request_tx_url")).strip()
                if payload.get("request_tx_url") is not None
                else None
            ),
            "settlement_finalized": bool(payload.get("settlement_finalized")),
            "classified_claim_count": max(int(payload.get("classified_claim_count") or 0), 0),
            "eligible_claim_count": max(int(payload.get("eligible_claim_count") or 0), 0),
            "claimant_withdrawn_count": max(
                int(payload.get("claimant_withdrawn_count") or 0),
                0,
            ),
            "eligible_stake_wei": max(int(payload.get("eligible_stake_wei") or 0), 0),
            "distributable_bounty_wei": max(
                int(payload.get("distributable_bounty_wei") or 0),
                0,
            ),
            "cumulative_bounty_withdrawn_wei": max(
                int(payload.get("cumulative_bounty_withdrawn_wei") or 0),
                0,
            ),
            "requester_refund_available": bool(payload.get("requester_refund_available")),
            "requester_refund_withdrawn": bool(payload.get("requester_refund_withdrawn")),
            "requester_refund_wei": max(int(payload.get("requester_refund_wei") or 0), 0),
            "filters": self._normalize_marketplace_filters(payload.get("filters")),
            "metadata": (
                dict(payload.get("metadata"))
                if isinstance(payload.get("metadata"), dict)
                else {}
            ),
        }

    def _normalize_marketplace_filters(
        self,
        filters: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if not isinstance(filters, dict):
            filters = {}
        minimum_stake_wei = max(int(filters.get("minimum_stake_wei") or 0), 0)
        whitelist_mode = str(filters.get("whitelist_mode") or "open").strip().lower()
        if whitelist_mode not in {"open", "allowlist"}:
            whitelist_mode = "open"
        allowed_service_ids = sorted(
            {
                str(service_id).strip()
                for service_id in filters.get("allowed_service_ids", [])
                if str(service_id).strip()
            }
        )
        required_identity_service_id = str(
            filters.get("required_identity_service_id") or ""
        ).strip() or None
        required_identity_agent_id = filters.get("required_identity_agent_id")
        if required_identity_agent_id in ("", None):
            normalized_agent_id = None
        else:
            normalized_agent_id = int(required_identity_agent_id)
        required_identity_registry = str(
            filters.get("required_identity_registry") or ""
        ).strip() or None
        return {
            "minimum_stake_wei": minimum_stake_wei,
            "whitelist_mode": whitelist_mode,
            "allowed_service_ids": allowed_service_ids,
            "required_identity_service_id": required_identity_service_id,
            "required_identity_agent_id": normalized_agent_id,
            "required_identity_registry": required_identity_registry,
        }

    def _sync_audit_request_record(self, record: dict[str, Any]) -> dict[str, Any]:
        if self.publisher is None:
            return record
        request_id = str(record.get("request_id") or "").strip()
        if not request_id.isdigit():
            return record

        try:
            onchain_request = self.publisher.get_audit_request(int(request_id))
        except Exception:
            return record
        try:
            onchain_settlement = self.publisher.get_audit_request_settlement(int(request_id))
        except Exception:
            onchain_settlement = None
        try:
            refund_preview = self.publisher.preview_audit_request_refund(int(request_id))
        except Exception:
            refund_preview = None

        synced = deepcopy(record)
        synced["status"] = onchain_request.state
        synced["requester"] = onchain_request.requester_address.lower()
        synced["contract_address"] = onchain_request.target_address.lower()
        synced["chain_id"] = self.contract_config.chain_id
        synced["bounty_wei"] = onchain_request.bounty_wei
        synced["protocol_fee_wei"] = (
            int(onchain_settlement.protocol_fee_wei)
            if onchain_settlement is not None
            else 0
        )
        synced["claim_count"] = onchain_request.claim_count
        synced["created_at"] = self._isoformat_unix_timestamp(onchain_request.created_at)
        synced["response_window_end"] = self._isoformat_unix_timestamp(
            onchain_request.response_window_end
        )
        synced["settlement_finalized"] = (
            bool(onchain_settlement.finalized) if onchain_settlement is not None else False
        )
        synced["classified_claim_count"] = (
            int(onchain_settlement.classified_claim_count)
            if onchain_settlement is not None
            else 0
        )
        synced["eligible_claim_count"] = (
            int(onchain_settlement.eligible_claim_count)
            if onchain_settlement is not None
            else 0
        )
        synced["claimant_withdrawn_count"] = (
            int(onchain_settlement.claimant_withdrawn_count)
            if onchain_settlement is not None
            else 0
        )
        synced["eligible_stake_wei"] = (
            int(onchain_settlement.eligible_stake_wei)
            if onchain_settlement is not None
            else 0
        )
        synced["distributable_bounty_wei"] = (
            int(onchain_settlement.distributable_bounty_wei)
            if onchain_settlement is not None
            else 0
        )
        synced["cumulative_bounty_withdrawn_wei"] = (
            int(onchain_settlement.cumulative_bounty_withdrawn_wei)
            if onchain_settlement is not None
            else 0
        )
        synced["requester_refund_available"] = (
            bool(refund_preview.available) if refund_preview is not None else False
        )
        synced["requester_refund_withdrawn"] = (
            bool(onchain_settlement.requester_refund_withdrawn)
            if onchain_settlement is not None
            else False
        )
        synced["requester_refund_wei"] = (
            int(refund_preview.refund_wei) if refund_preview is not None else 0
        )
        filters = self._normalize_marketplace_filters(synced.get("filters"))
        if int(filters.get("minimum_stake_wei") or 0) == 0:
            filters["minimum_stake_wei"] = int(
                onchain_request.eligibility["minimum_stake_wei"]
            )
        if (
            filters.get("whitelist_mode") != "allowlist"
            and bool(onchain_request.eligibility["allowlist_enabled"])
        ):
            filters["whitelist_mode"] = "allowlist"
        if (
            filters.get("required_identity_registry") is None
            and onchain_request.eligibility["identity_registry"] is not None
        ):
            filters["required_identity_registry"] = str(
                onchain_request.eligibility["identity_registry"]
            ).lower()
        if (
            filters.get("required_identity_agent_id") is None
            and int(onchain_request.eligibility["required_agent_id"]) > 0
        ):
            filters["required_identity_agent_id"] = int(
                onchain_request.eligibility["required_agent_id"]
            )
        synced["filters"] = filters
        metadata = (
            deepcopy(synced.get("metadata"))
            if isinstance(synced.get("metadata"), dict)
            else {}
        )
        metadata["onchain_eligibility"] = onchain_request.eligibility
        metadata["allowlisted_auditor_addresses"] = list(
            onchain_request.eligibility.get("allowlisted_auditor_addresses") or []
        )
        synced["metadata"] = metadata
        return synced

    def _build_audit_request_claim_payload(
        self, record: dict[str, Any]
    ) -> dict[str, Any]:
        onchain = deepcopy(record.get("onchain")) if isinstance(record.get("onchain"), dict) else {}
        request_claim_id = onchain.get("request_claim_id")
        settlement_preview = None
        if self.publisher is not None and request_claim_id is not None:
            try:
                onchain_claim = self.publisher.get_audit_request_claim(int(request_claim_id))
            except Exception:
                onchain_claim = None
            else:
                onchain["claim_state"] = onchain_claim.state
                onchain["published_at"] = self._isoformat_unix_timestamp(
                    onchain_claim.submitted_at
                )
                onchain["stake_wei"] = onchain_claim.stake_wei
                onchain["agent_id"] = onchain_claim.agent_id
                onchain["agent_registry"] = onchain_claim.agent_registry.lower()
                onchain["auditor_address"] = onchain_claim.auditor_address.lower()
            try:
                settlement_preview = self.publisher.preview_audit_request_claim_settlement(
                    int(request_claim_id)
                )
            except Exception:
                settlement_preview = None

        service = self._record_auditor_service(record)
        report = record["report"]
        return {
            "claim_id": str(onchain.get("request_claim_id") or ""),
            "request_id": str(onchain.get("request_id") or ""),
            "audit_id": record["id"],
            "claim_state": str(onchain.get("claim_state") or "submitted"),
            "auditor_service_id": str(service.get("service_id") or ""),
            "agent_id": (
                int(onchain["agent_id"])
                if onchain.get("agent_id") is not None
                else (int(service["agent_id"]) if service.get("agent_id") is not None else None)
            ),
            "agent_registry": (
                str(onchain.get("agent_registry"))
                if onchain.get("agent_registry") is not None
                else (
                    str(service["agent_registry"])
                    if service.get("agent_registry") is not None
                    else None
                )
            ),
            "auditor_address": (
                str(onchain.get("auditor_address"))
                if onchain.get("auditor_address") is not None
                else None
            ),
            "stake_wei": int(onchain.get("stake_wei") or 0),
            "submitted_at": (
                str(onchain.get("published_at"))
                if onchain.get("published_at") is not None
                else None
            ),
            "report_hash": str(report.get("report_hash") or ""),
            "metadata_hash": str(report.get("metadata_hash") or ""),
            "max_severity": int(report.get("max_severity") or 0),
            "finding_count": int(report.get("finding_count") or len(report.get("findings") or [])),
            "tx_hash": (
                str(onchain.get("claim_tx_hash") or onchain.get("publish_tx_hash") or "")
                or None
            ),
            "tx_url": (
                str(onchain.get("claim_tx_url") or onchain.get("publish_tx_url") or "")
                or None
            ),
            "status": str(record.get("status") or "draft"),
            "target_contract": record["contract_address"],
            "eligible_for_bounty": (
                bool(settlement_preview.eligible)
                if settlement_preview is not None
                else False
            ),
            "settlement_withdrawn": (
                bool(settlement_preview.withdrawn)
                if settlement_preview is not None
                else False
            ),
            "bounty_share_wei": (
                int(settlement_preview.bounty_share_wei)
                if settlement_preview is not None
                else 0
            ),
            "settlement_payout_wei": (
                int(settlement_preview.payout_wei)
                if settlement_preview is not None
                else 0
            ),
            "challenge_policy": (
                deepcopy(onchain.get("challenge_policy"))
                if isinstance(onchain.get("challenge_policy"), dict)
                else self._normalize_challenge_policy(None)
            ),
        }

    def _upsert_audit_request_record(self, record: dict[str, Any]) -> None:
        path = self._audit_request_catalog_path()
        items: list[dict[str, Any]] = []
        if path.exists():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                payload = {}
            if isinstance(payload, dict) and isinstance(payload.get("items"), list):
                items = [item for item in payload["items"] if isinstance(item, dict)]
        request_id = str(record["request_id"])
        items = [
            item
            for item in items
            if str(item.get("request_id") or item.get("id") or "").strip() != request_id
        ]
        items.append(deepcopy(record))
        path.write_text(
            json.dumps({"items": items}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _build_auditor_matches(self, filters: dict[str, Any]) -> list[dict[str, Any]]:
        minimum_stake_wei = int(filters.get("minimum_stake_wei") or 0)
        whitelist_mode = str(filters.get("whitelist_mode") or "open")
        allowed_service_ids = list(filters.get("allowed_service_ids") or [])
        required_identity_service_id = filters.get("required_identity_service_id")
        required_identity_agent_id = filters.get("required_identity_agent_id")
        required_identity_registry = filters.get("required_identity_registry")
        normalized_registry = (
            str(required_identity_registry).strip().lower()
            if required_identity_registry
            else None
        )

        auditor_matches: list[dict[str, Any]] = []
        for service in self.list_auditor_services():
            reputation = service.get("reputation")
            stake_preview_wei = None
            if isinstance(reputation, dict):
                raw_stake_preview = reputation.get("total_stake_wei")
                if raw_stake_preview is not None:
                    stake_preview_wei = int(raw_stake_preview)

            reasons: list[str] = []
            if minimum_stake_wei > 0:
                if stake_preview_wei is None:
                    reasons.append(
                        "Stake preview unavailable for the minimum commitment filter."
                    )
                elif stake_preview_wei < minimum_stake_wei:
                    reasons.append("Observed stake preview is below the requested minimum.")

            if whitelist_mode == "allowlist":
                if not allowed_service_ids:
                    reasons.append(
                        "Allowlist mode is enabled but no auditor services are selected."
                    )
                elif service["service_id"] not in allowed_service_ids:
                    reasons.append("Auditor is outside the current allowlist preview.")

            if required_identity_service_id and (
                service["service_id"] != required_identity_service_id
            ):
                reasons.append("Service ID does not match the required registered identity.")

            if required_identity_agent_id is not None and (
                service.get("agent_id") != required_identity_agent_id
            ):
                reasons.append("Agent ID does not match the required registered identity.")

            service_registry = str(service.get("agent_registry") or "").strip().lower()
            if normalized_registry and service_registry != normalized_registry:
                reasons.append(
                    "Agent registry does not match the required registered identity."
                )

            matches = len(reasons) == 0
            auditor_matches.append(
                {
                    "service_id": service["service_id"],
                    "name": service["name"],
                    "agent_id": service.get("agent_id"),
                    "agent_registry": service.get("agent_registry"),
                    "reputation": reputation if isinstance(reputation, dict) else None,
                    "stake_preview_wei": stake_preview_wei,
                    "eligibility": {
                        "matches": matches,
                        "approximate": True,
                        "reasons": reasons or ["Matches the current preview filters."],
                    },
                }
            )
        return auditor_matches

    def build_marketplace_preview(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized_filters = self._normalize_marketplace_filters(payload.get("filters"))
        bounty_wei = max(int(payload.get("bounty_wei") or 0), 0)
        protocol_fee_wei = max(int(payload.get("protocol_fee_wei") or 0), 0)
        contract_address = str(payload.get("contract_address") or "").strip() or None
        target_contract = (
            self._normalize_target_key(contract_address) if contract_address else None
        )
        auditor_matches = self._build_auditor_matches(normalized_filters)

        eligible_count = sum(
            1
            for item in auditor_matches
            if bool(item["eligibility"]["matches"])
        )
        return {
            "target_contract": target_contract,
            "request_state": "preview_only",
            "chain_context": {
                "authority": "chain_authoritative",
                "network": self.contract_config.network,
                "chain_id": self.contract_config.chain_id,
                "required_stake_wei": self.contract_config.required_stake_wei,
                "challenge_window_seconds": self.contract_config.challenge_window_seconds,
            },
            "cost_breakdown": {
                "authority": "api_preview",
                "bounty_wei": bounty_wei,
                "protocol_fee_wei": protocol_fee_wei,
                "total_wei": bounty_wei + protocol_fee_wei,
            },
            "filters": normalized_filters,
            "eligibility_summary": {
                "authority": "api_preview",
                "total_auditors": len(auditor_matches),
                "eligible_auditors": eligible_count,
                "approximate": True,
            },
            "auditor_matches": auditor_matches,
            "preview_disclaimer": (
                "Eligible auditor counts are API-derived previews only. Final request "
                "eligibility is enforced on-chain at claim submission time."
            ),
        }

    def _resolve_request_required_identity(
        self, filters: dict[str, Any]
    ) -> dict[str, Any]:
        required_identity_service_id = filters.get("required_identity_service_id")
        required_identity_agent_id = filters.get("required_identity_agent_id")
        required_identity_registry = filters.get("required_identity_registry")

        if required_identity_service_id:
            service = self.get_auditor_service(str(required_identity_service_id))
            if service is None:
                raise ValueError(
                    f"unknown required_identity_service_id: {required_identity_service_id}"
                )
            service_agent_id = service.get("agent_id")
            service_agent_registry = service.get("agent_registry")
            if not isinstance(service_agent_id, int) or not service_agent_registry:
                raise ValueError(
                    "required_identity_service_id must resolve to an auditor service "
                    "with canonical on-chain identity metadata"
                )
            normalized_service_registry = self._normalize_target_key(
                service_agent_registry
            )
            if (
                required_identity_agent_id is not None
                and int(required_identity_agent_id) != int(service_agent_id)
            ):
                raise ValueError(
                    "required_identity_service_id does not match required_identity_agent_id"
                )
            if required_identity_registry and (
                self._normalize_target_key(required_identity_registry)
                != normalized_service_registry
            ):
                raise ValueError(
                    "required_identity_service_id does not match required_identity_registry"
                )
            return {
                "service_id": str(required_identity_service_id),
                "agent_id": int(service_agent_id),
                "agent_registry": normalized_service_registry,
            }

        if (required_identity_agent_id is None) != (required_identity_registry is None):
            raise ValueError(
                "required identity filters must include both required_identity_registry "
                "and required_identity_agent_id"
            )
        if required_identity_agent_id is None or required_identity_registry is None:
            return {
                "service_id": None,
                "agent_id": None,
                "agent_registry": None,
            }
        normalized_agent_id = int(required_identity_agent_id)
        if normalized_agent_id <= 0:
            raise ValueError("required_identity_agent_id must be greater than zero")
        return {
            "service_id": None,
            "agent_id": normalized_agent_id,
            "agent_registry": self._normalize_target_key(required_identity_registry),
        }

    def _resolve_request_allowlist(
        self, allowed_service_ids: list[str], *, enabled: bool
    ) -> dict[str, Any]:
        if not enabled:
            return {
                "auditor_addresses": [],
                "services": [],
            }
        if not allowed_service_ids:
            raise ValueError("allowlist mode requires at least one allowed_service_id")

        allowlisted_addresses: list[str] = []
        seen_addresses: set[str] = set()
        resolved_services: list[dict[str, Any]] = []
        for service_id in allowed_service_ids:
            service = self.get_auditor_service(service_id)
            if service is None:
                raise ValueError(f"unknown allowlisted auditor service: {service_id}")
            agent_id = service.get("agent_id")
            agent_registry = service.get("agent_registry")
            if not isinstance(agent_id, int) or not agent_registry:
                raise ValueError(
                    f"auditor service {service_id} is missing canonical on-chain identity"
                )
            owner_address = self.publisher.resolve_identity_owner(
                agent_registry=str(agent_registry),
                agent_id=int(agent_id),
            )
            normalized_owner = self._normalize_target_key(owner_address)
            if normalized_owner not in seen_addresses:
                seen_addresses.add(normalized_owner)
                allowlisted_addresses.append(normalized_owner)
            resolved_services.append(
                {
                    "service_id": service["service_id"],
                    "name": service["name"],
                    "agent_id": int(agent_id),
                    "agent_registry": self._normalize_target_key(agent_registry),
                    "auditor_address": normalized_owner,
                }
            )
        return {
            "auditor_addresses": allowlisted_addresses,
            "services": resolved_services,
        }

    def _request_eligibility_reasons(
        self, *, request_record: dict[str, Any], auditor_service: dict[str, Any]
    ) -> list[str]:
        reasons: list[str] = []
        filters = self._normalize_marketplace_filters(request_record.get("filters"))
        metadata = (
            request_record.get("metadata")
            if isinstance(request_record.get("metadata"), dict)
            else {}
        )

        reputation = auditor_service.get("reputation")
        stake_preview_wei = None
        if isinstance(reputation, dict):
            raw_stake_preview = reputation.get("total_stake_wei")
            if raw_stake_preview is not None:
                stake_preview_wei = int(raw_stake_preview)
        minimum_stake_wei = int(filters.get("minimum_stake_wei") or 0)
        if minimum_stake_wei > 0:
            if stake_preview_wei is None:
                reasons.append(
                    "Stake preview unavailable for the minimum commitment filter."
                )
            elif stake_preview_wei < minimum_stake_wei:
                reasons.append("Observed stake preview is below the requested minimum.")

        onchain_eligibility = (
            metadata.get("onchain_eligibility")
            if isinstance(metadata.get("onchain_eligibility"), dict)
            else {}
        )
        allowlist_enabled = bool(
            onchain_eligibility.get("allowlist_enabled")
            or filters.get("whitelist_mode") == "allowlist"
        )
        allowlisted_auditors = {
            self._normalize_target_key(value)
            for value in (
                metadata.get("allowlisted_auditor_addresses")
                or onchain_eligibility.get("allowlisted_auditor_addresses")
                or []
            )
            if str(value).strip()
        }
        if allowlist_enabled:
            if not allowlisted_auditors:
                allowed_service_ids = list(filters.get("allowed_service_ids") or [])
                if not allowed_service_ids:
                    reasons.append(
                        "Allowlist mode is enabled but no auditor services are selected."
                    )
                elif auditor_service["service_id"] not in allowed_service_ids:
                    reasons.append(
                        "Auditor is outside the current allowlist preview."
                    )
            else:
                agent_id = auditor_service.get("agent_id")
                agent_registry = auditor_service.get("agent_registry")
                if not isinstance(agent_id, int) or not agent_registry or self.publisher is None:
                    reasons.append(
                        "Auditor owner address could not be resolved against the request allowlist."
                    )
                else:
                    try:
                        owner_address = self.publisher.resolve_identity_owner(
                            agent_registry=str(agent_registry),
                            agent_id=int(agent_id),
                        )
                    except Exception:
                        reasons.append(
                            "Auditor owner address could not be resolved against the request allowlist."
                        )
                    else:
                        if self._normalize_target_key(owner_address) not in allowlisted_auditors:
                            reasons.append(
                                "Resolved auditor owner address is outside the stored request allowlist."
                            )

        required_identity_registry = (
            str(onchain_eligibility.get("identity_registry") or "").strip()
            or filters.get("required_identity_registry")
        )
        required_identity_agent_id = onchain_eligibility.get("required_agent_id")
        if not required_identity_agent_id:
            required_identity_agent_id = filters.get("required_identity_agent_id")
        normalized_required_registry = (
            self._normalize_target_key(required_identity_registry)
            if required_identity_registry
            else None
        )
        if normalized_required_registry:
            service_registry = str(auditor_service.get("agent_registry") or "").strip()
            if self._normalize_target_key(service_registry) != normalized_required_registry:
                reasons.append(
                    "Agent registry does not match the required registered identity."
                )
        if required_identity_agent_id is not None and (
            auditor_service.get("agent_id") != int(required_identity_agent_id)
        ):
            reasons.append("Agent ID does not match the required registered identity.")

        return reasons

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

    def _normalize_challenge_policy(
        self, policy: dict[str, Any] | None
    ) -> dict[str, Any]:
        payload = deepcopy(policy) if isinstance(policy, dict) else {}
        normalized = deepcopy(_DEFAULT_CHALLENGE_POLICY)
        normalized["policy_version"] = str(
            payload.get("policy_version") or normalized["policy_version"]
        )

        allowed_evidence_types = payload.get("allowed_evidence_types")
        if isinstance(allowed_evidence_types, list) and allowed_evidence_types:
            normalized_types = sorted(
                {
                    str(item).strip()
                    for item in allowed_evidence_types
                    if str(item).strip() in {"deterministic_fixture", "executable_test"}
                }
            )
            if not normalized_types:
                raise ValueError(
                    "challenge_policy.allowed_evidence_types must include supported evidence types"
                )
            normalized["allowed_evidence_types"] = normalized_types

        threshold = str(
            payload.get("min_severity_threshold")
            or normalized["min_severity_threshold"]
        ).strip().lower()
        if threshold == "informational":
            threshold = "info"
        if threshold not in _SEVERITY_RANKING:
            raise ValueError(
                "challenge_policy.min_severity_threshold must be one of info, low, medium, high, or critical"
            )
        normalized["min_severity_threshold"] = threshold

        normalized["allow_informational_only"] = bool(
            payload.get(
                "allow_informational_only", normalized["allow_informational_only"]
            )
        )
        normalized["requires_material_incorrectness"] = bool(
            payload.get(
                "requires_material_incorrectness",
                normalized["requires_material_incorrectness"],
            )
        )
        admissibility_mode = str(
            payload.get("admissibility_mode") or normalized["admissibility_mode"]
        ).strip().lower()
        if admissibility_mode not in {"broad", "strict"}:
            raise ValueError(
                "challenge_policy.admissibility_mode must be broad or strict"
            )
        normalized["admissibility_mode"] = admissibility_mode
        return normalized

    def _challenge_policy_for_record(self, record: dict[str, Any]) -> dict[str, Any]:
        onchain = record.get("onchain")
        if isinstance(onchain, dict):
            return self._normalize_challenge_policy(onchain.get("challenge_policy"))
        return self._normalize_challenge_policy(None)

    def _request_claim_context(self, record: dict[str, Any]) -> tuple[dict[str, Any], int, int]:
        onchain = record.get("onchain")
        if not isinstance(onchain, dict):
            raise ValueError("audit must be published before challenge")
        request_id = onchain.get("request_id")
        request_claim_id = onchain.get("request_claim_id")
        if not isinstance(request_id, int) or not isinstance(request_claim_id, int):
            raise ValueError("published request claim is missing its on-chain request metadata")
        request_record = self.get_audit_request(str(request_id))
        if request_record is None:
            raise ValueError("request claim is missing its parent audit request")
        return request_record, request_id, request_claim_id

    def _configured_request_claim_challenger_identity(
        self, record: dict[str, Any]
    ) -> tuple[str, int]:
        _request_record, request_id, _request_claim_id = self._request_claim_context(record)
        service = self.contract_config.auditor_service
        agent_registry = str(
            service.agent_registry or self.contract_config.auditor_agent_registry or ""
        ).strip()
        agent_id = service.agent_id or self.contract_config.auditor_agent_id
        if not agent_registry or not isinstance(agent_id, int) or agent_id <= 0:
            raise ValueError(
                "configured auditor service is missing the canonical on-chain identity required for request-claim challenges"
            )

        onchain = record.get("onchain") or {}
        current_registry = str(onchain.get("agent_registry") or "").strip().lower()
        current_agent_id = onchain.get("agent_id")
        current_auditor_address = str(onchain.get("auditor_address") or "").strip().lower()
        configured_address = (
            self.publisher.account.address.lower() if self.publisher is not None else ""
        )
        if (
            current_registry == agent_registry.lower()
            and current_agent_id == agent_id
        ) or (configured_address and current_auditor_address == configured_address):
            raise ValueError("configured auditor cannot challenge its own request claim")

        eligibility = self.build_audit_request_eligibility(str(request_id), service.service_id)
        if eligibility is None or not bool(eligibility.get("eligible")):
            reasons = (
                ", ".join(str(item) for item in (eligibility or {}).get("reasons") or [])
                if isinstance(eligibility, dict)
                else ""
            )
            detail = f" {reasons}" if reasons else ""
            raise ValueError(
                "configured auditor service is not eligible to challenge this request claim."
                + detail
            )
        return agent_registry, agent_id

    def _admissible_material_incorrectness(
        self, verification_dossier: dict[str, Any] | None
    ) -> bool:
        comparison = (
            verification_dossier.get("comparison")
            if isinstance(verification_dossier, dict)
            and isinstance(verification_dossier.get("comparison"), dict)
            else {}
        )
        return str(comparison.get("status") or "") in {
            "likely_new_issue",
            "contradicts_audit_claim",
        }

    def _estimate_challenge_severity(
        self,
        *,
        record: dict[str, Any],
        verification_result: Any | None,
        verification_dossier: dict[str, Any] | None,
    ) -> str | None:
        report = record.get("report")
        findings = report.get("findings") if isinstance(report, dict) else None
        finding_index: dict[str, str] = {}
        if isinstance(findings, list):
            for finding in findings:
                if not isinstance(finding, dict):
                    continue
                finding_id = str(finding.get("finding_id") or "").strip()
                severity = str(finding.get("severity") or "info").strip().lower()
                if severity == "informational":
                    severity = "info"
                if finding_id:
                    finding_index[finding_id] = severity

        matched_ids = getattr(verification_result, "matched_findings", None)
        if not isinstance(matched_ids, list) and isinstance(verification_dossier, dict):
            comparison = verification_dossier.get("comparison")
            if isinstance(comparison, dict):
                matched_ids = comparison.get("matched_finding_ids")
        matched_severities = [
            finding_index.get(str(finding_id).strip())
            for finding_id in (matched_ids or [])
            if finding_index.get(str(finding_id).strip()) is not None
        ]
        if matched_severities:
            return max(matched_severities, key=self._severity_rank)

        comparison_status = ""
        if isinstance(verification_dossier, dict):
            comparison = verification_dossier.get("comparison")
            if isinstance(comparison, dict):
                comparison_status = str(comparison.get("status") or "")
        claim = getattr(verification_result, "challenge_claim", None)
        claim_type = (
            str(getattr(claim, "claim_type", "") or "").strip().lower()
            if claim is not None
            else ""
        )
        if claim_type in {"reentrancy", "access_control"}:
            return "high"
        if claim_type == "unchecked_external_call":
            return "medium"
        if comparison_status == "contradicts_audit_claim":
            return "high"
        if comparison_status == "likely_new_issue":
            return "medium"
        return None

    def _severity_rank(self, severity: str) -> int:
        normalized = str(severity or "info").strip().lower()
        if normalized == "informational":
            normalized = "info"
        return _SEVERITY_RANKING.get(normalized, 0)

    def _evaluate_challenge_policy(
        self,
        *,
        record: dict[str, Any],
        challenge_policy: dict[str, Any],
        evidence_type: str,
        verification_result: Any | None,
        verification_dossier: dict[str, Any] | None,
    ) -> dict[str, Any]:
        allowed_evidence_types = set(challenge_policy["allowed_evidence_types"])
        if evidence_type not in allowed_evidence_types:
            return {
                "admissible": False,
                "status": "inadmissible_evidence_type",
                "rationale": (
                    f"Challenge evidence type {evidence_type} is outside the published challenge policy."
                ),
                "summary": "Challenge evidence type is outside the published challenge policy.",
                "detail": (
                    "The published claim only accepts "
                    + ", ".join(sorted(allowed_evidence_types))
                    + f", but {evidence_type} was submitted."
                ),
            }

        verification_status = str(
            getattr(verification_result, "status", "") or ""
        ).strip()
        if (
            challenge_policy["admissibility_mode"] == "strict"
            and verification_status != "verified"
        ):
            return {
                "admissible": False,
                "status": "inadmissible_policy_scope",
                "rationale": (
                    "Strict challenge policy only admits verifier-confirmed challenges."
                ),
                "summary": "Challenge falls outside the published challenge policy.",
                "detail": (
                    "The published claim uses strict admissibility, so challenges that do "
                    "not reach verifier-confirmed status are not admitted."
                ),
            }

        if (
            challenge_policy["requires_material_incorrectness"]
            and not self._admissible_material_incorrectness(verification_dossier)
        ):
            return {
                "admissible": False,
                "status": "inadmissible_policy_scope",
                "rationale": (
                    "Published challenge policy requires material incorrectness."
                ),
                "summary": "Challenge falls outside the published challenge policy.",
                "detail": (
                    "The published claim only admits challenges that demonstrate material "
                    "incorrectness, but this verifier result did not reach that threshold."
                ),
            }

        estimated_severity = self._estimate_challenge_severity(
            record=record,
            verification_result=verification_result,
            verification_dossier=verification_dossier,
        )
        if (
            not challenge_policy["allow_informational_only"]
            and estimated_severity == "info"
        ):
            return {
                "admissible": False,
                "status": "inadmissible_severity_below_threshold",
                "rationale": (
                    "Published challenge policy excludes informational-only disagreements."
                ),
                "summary": "Challenge severity is below the published challenge policy threshold.",
                "detail": (
                    "The verifier could only support an informational disagreement, which "
                    "this claim's challenge policy does not admit."
                ),
            }

        min_threshold = str(challenge_policy["min_severity_threshold"])
        if (
            estimated_severity is None
            and self._severity_rank(min_threshold) > self._severity_rank("info")
        ):
            return {
                "admissible": False,
                "status": "inadmissible_severity_below_threshold",
                "rationale": (
                    "Verifier output did not establish a challenge severity high enough "
                    "for the published threshold."
                ),
                "summary": "Challenge severity is below the published challenge policy threshold.",
                "detail": (
                    "The challenge policy requires severity "
                    f"{min_threshold} or above, but the verifier could not determine a "
                    "supported severity at that level."
                ),
            }
        if (
            estimated_severity is not None
            and self._severity_rank(estimated_severity)
            < self._severity_rank(min_threshold)
        ):
            return {
                "admissible": False,
                "status": "inadmissible_severity_below_threshold",
                "rationale": (
                    "Verifier-supported challenge severity is below the published threshold."
                ),
                "summary": "Challenge severity is below the published challenge policy threshold.",
                "detail": (
                    "The challenge policy requires severity "
                    f"{min_threshold} or above, but the verifier-supported severity was "
                    f"{estimated_severity}."
                ),
            }
        return {
            "admissible": True,
            "status": "admissible",
            "rationale": "Challenge is within the published challenge policy.",
            "summary": "Challenge is within the published challenge policy.",
            "detail": "Challenge admissibility checks passed.",
        }

    def publish_audit(
        self,
        audit_id: str,
        stake_wei: int,
        agent_identity: str | None,
        challenge_policy: dict[str, Any] | None = None,
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
        self._assert_snapshot_publishable(record)
        agent = self._record_agent_profile(record)
        agent_identity = agent_identity or str(agent.get("id") or self.contract_config.auditor.id)
        report = record["report"]
        snapshot = self._record_snapshot_metadata(record)
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
            "snapshot_block_number": snapshot["snapshot_block_number"],
            "snapshot_block_hash": snapshot["snapshot_block_hash"],
            "target_code_hash_at_snapshot": snapshot["target_code_hash_at_snapshot"],
            "proxy_kind": snapshot["proxy_kind"],
            "proxy_resolution_status": snapshot["proxy_resolution_status"],
            "proxy_resolution_detail": snapshot["proxy_resolution_detail"],
            "implementation_address_at_snapshot": snapshot[
                "implementation_address_at_snapshot"
            ],
            "implementation_code_hash_at_snapshot": snapshot[
                "implementation_code_hash_at_snapshot"
            ],
            "challenge_policy": self._normalize_challenge_policy(challenge_policy),
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
        challenge_policy = self._challenge_policy_for_record(record)
        if (
            evidence_type == "executable_test"
            and record["submission"]["input_kind"] != "deployed_address"
        ):
            raise ValueError(
                "executable_test challenge evidence is only supported for deployed_address audits"
            )
        snapshot = self._record_snapshot_metadata(record)
        materialized_evidence_manifest = deepcopy(evidence_manifest)
        if (
            evidence_type == "executable_test"
            and snapshot["snapshot_block_number"] is not None
            and isinstance(materialized_evidence_manifest, dict)
            and materialized_evidence_manifest.get("pinned_block_number") is not None
            and int(materialized_evidence_manifest["pinned_block_number"])
            != int(snapshot["snapshot_block_number"])
        ):
            raise ValueError(
                "executable challenge evidence must use the audit snapshot block"
            )
        if (
            evidence_type == "executable_test"
            and snapshot["snapshot_block_number"] is not None
            and isinstance(materialized_evidence_manifest, dict)
            and materialized_evidence_manifest.get("pinned_block_number") is None
        ):
            materialized_evidence_manifest["pinned_block_number"] = int(
                snapshot["snapshot_block_number"]
            )
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
            evidence_manifest=materialized_evidence_manifest,
            chain_id=int(record["onchain"].get("chain_id") or self.contract_config.chain_id),
        )
        onchain = record["onchain"]
        request_claim_id = onchain.get("request_claim_id")
        onchain_audit_id = onchain.get("audit_id")
        if isinstance(request_claim_id, int):
            challenger_agent_registry, challenger_agent_id = (
                self._configured_request_claim_challenger_identity(record)
            )
            challenge_result = self.publisher.challenge_audit_request_claim(
                claim_id=request_claim_id,
                agent_registry=challenger_agent_registry,
                agent_id=challenger_agent_id,
                evidence_hash=evidence_hash,
                challenge_bond_wei=self.contract_config.required_challenge_bond_wei,
            )
            onchain["claim_state"] = "challenged"
        else:
            if not isinstance(onchain_audit_id, int):
                raise ValueError("published audit is missing its on-chain audit id")
            challenge_result = self.publisher.challenge_audit(
                audit_id=onchain_audit_id,
                evidence_hash=evidence_hash,
                challenge_bond_wei=self.contract_config.required_challenge_bond_wei,
            )
        challenge_record = {
            "challenger": challenger,
            "challenger_address": challenge_result.challenger_address,
            "proof_uri": proof_uri,
            "evidence_hash": challenge_result.evidence_hash,
            "evidence_type": evidence_type,
            "execution_env": execution_env,
            "evidence_manifest": deepcopy(materialized_evidence_manifest),
            "submitted_at": datetime.now(UTC).isoformat(),
            "verifier": (
                EXECUTABLE_VERIFIER_NAME
                if evidence_type == "executable_test"
                else PROOF_URI_VERIFIER_NAME
            ),
            "status": "opened",
            "resolution_path": "manual_fallback",
            "verification_status": "pending",
            "verification_summary": "On-chain challenge submitted. Verification still pending.",
            "verification_detail": None,
            "verification_case_id": None,
            "advisory_verdict": None,
            "execution_log": None,
            "matched_findings": [],
            "unmatched_findings": [],
            "challenge_hash": challenge_result.evidence_hash,
            "challenge_bond_wei": challenge_result.challenge_bond_wei,
            "chain_id": challenge_result.chain_id,
            "challenge_tx_hash": challenge_result.tx_hash,
            "challenge_tx_url": self.contract_config.transaction_url(
                challenge_result.tx_hash
            ),
        }
        record["status"] = "challenged"
        record["challenge"] = challenge_record
        self.store.write(audit_id, record)

        verification_result = None
        verification_dossier: dict[str, Any]
        policy_decision = self._evaluate_challenge_policy(
            record=record,
            challenge_policy=challenge_policy,
            evidence_type=evidence_type,
            verification_result=None,
            verification_dossier=None,
        )
        if policy_decision["status"] == "inadmissible_evidence_type":
            verification_dossier = self._normalize_verification_dossier(
                {
                    "schema_version": "challenge-verifier-dossier/v1",
                    "verifier_version": str(challenge_record.get("verifier") or ""),
                    "evidence_type": evidence_type,
                    "integrity": {
                        "status": "valid",
                        "committed_evidence_hash": challenge_result.evidence_hash,
                    },
                    "execution": {
                        "status": (
                            "not_executed"
                            if evidence_type == "deterministic_fixture"
                            else "unknown"
                        ),
                        "execution_env": execution_env,
                    },
                    "claim": None,
                    "comparison": {
                        "status": "not_assessed",
                        "confidence": "unknown",
                        "rationale": None,
                        "matched_finding_ids": [],
                        "matched_findings": [],
                        "unmatched_signals": [],
                        "disagreement_status": "not_checked",
                        "disagreement_detail": None,
                    },
                    "policy": {
                        "status": "rejected",
                        "advisory_only": False,
                        "recommended_resolution": "rejected",
                        "abstained": False,
                        "confidence": "high",
                        "rationale": policy_decision["rationale"],
                        "admissibility_status": policy_decision["status"],
                        "effective_policy": challenge_policy,
                    },
                    "model_metadata": {},
                },
                challenge=challenge_record,
            )
        else:
            verification_result = verifier.verify(
                EvidenceContext(
                    proof_uri=proof_uri,
                benchmark_id=str(record["report"].get("benchmark_id") or "unknown"),
                target_contract=record["contract_address"],
                published_report=deepcopy(record["report"]),
                evidence_type=evidence_type,
                execution_env=execution_env,
                evidence_manifest=deepcopy(materialized_evidence_manifest),
                chain_id=int(
                    record["onchain"].get("chain_id") or self.contract_config.chain_id
                ),
                rpc_url=self.contract_config.rpc_url,
                snapshot_block_number=snapshot["snapshot_block_number"],
                committed_evidence_hash=evidence_hash,
            )
        )
            verification_dossier = self._verification_dossier_payload(
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
            )
            policy_decision = self._evaluate_challenge_policy(
                record=record,
                challenge_policy=challenge_policy,
                evidence_type=evidence_type,
                verification_result=verification_result,
                verification_dossier=verification_dossier,
            )

        dossier_policy = (
            verification_dossier["policy"]
            if isinstance(verification_dossier.get("policy"), dict)
            else {}
        )
        dossier_policy["admissibility_status"] = policy_decision["status"]
        dossier_policy["effective_policy"] = challenge_policy
        if not policy_decision["admissible"]:
            dossier_policy["status"] = "rejected"
            dossier_policy["recommended_resolution"] = "rejected"
            dossier_policy["abstained"] = False
            dossier_policy["rationale"] = policy_decision["rationale"]
            dossier_policy["confidence"] = "high"
        verification_dossier["policy"] = dossier_policy

        challenge_record.update(
            {
                "verifier": (
                    verification_result.verifier
                    if verification_result is not None
                    else challenge_record["verifier"]
                ),
                "verification_status": (
                    verification_result.status
                    if verification_result is not None and policy_decision["admissible"]
                    else policy_decision["status"]
                ),
                "verification_summary": (
                    verification_result.summary
                    if verification_result is not None and policy_decision["admissible"]
                    else policy_decision["summary"]
                ),
                "verification_detail": (
                    verification_result.detail
                    if verification_result is not None and policy_decision["admissible"]
                    else policy_decision["detail"]
                ),
                "verification_case_id": (
                    verification_result.case_id if verification_result is not None else None
                ),
                "policy_admissibility_status": policy_decision["status"],
                "policy_admissibility_rationale": policy_decision["rationale"],
                "advisory_verdict": (
                    verification_result.resolution
                    if verification_result is not None and verification_result.advisory_only
                    else None
                ),
                "execution_log": (
                    verification_result.execution_log
                    if verification_result is not None
                    else None
                ),
                "matched_findings": (
                    verification_result.matched_findings
                    if verification_result is not None
                    else []
                ),
                "unmatched_findings": (
                    verification_result.unmatched_findings
                    if verification_result is not None
                    else []
                ),
                "verification_dossier": verification_dossier,
                "verification_dossier_path": f"/audits/{audit_id}/challenge/dossier",
            }
        )

        if (
            verification_result is not None
            and policy_decision["admissible"]
            and verification_result.status == "verified"
            and verification_result.upheld is not None
            and not verification_result.advisory_only
            and self.arbiter_client is not None
        ):
            try:
                if isinstance(request_claim_id, int):
                    resolution_result = (
                        self.arbiter_client.resolve_audit_request_claim_challenge(
                            claim_id=request_claim_id,
                            upheld=verification_result.upheld,
                        )
                    )
                    onchain["claim_state"] = (
                        "slashed" if verification_result.upheld else "resolved"
                    )
                else:
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
                        "gross_payout_wei": getattr(
                            resolution_result, "gross_payout_wei", resolution_result.payout_wei
                        ),
                        "resolution_fee_wei": getattr(
                            resolution_result, "resolution_fee_wei", 0
                        ),
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
        challenge = record["challenge"]
        if upheld and str(challenge.get("policy_admissibility_status") or "").startswith(
            "inadmissible_"
        ):
            raise ValueError("inadmissible challenges cannot be upheld")
        onchain = record.get("onchain", {})
        request_claim_id = onchain.get("request_claim_id") if isinstance(onchain, dict) else None
        onchain_audit_id = onchain.get("audit_id") if isinstance(onchain, dict) else None
        if not isinstance(request_claim_id, int) and not isinstance(onchain_audit_id, int):
            raise ValueError("challenged audit is missing its on-chain challenge target")
        if self.arbiter_client is None:
            raise OnchainConfigurationError(
                "On-chain resolution is not configured for this API instance."
            )

        if isinstance(request_claim_id, int):
            resolution_result = self.arbiter_client.resolve_audit_request_claim_challenge(
                claim_id=request_claim_id,
                upheld=upheld,
            )
            onchain["claim_state"] = "slashed" if upheld else "resolved"
        else:
            resolution_result = self.arbiter_client.resolve_challenge(
                audit_id=onchain_audit_id,
                upheld=upheld,
            )
        challenge.update(
            {
                "status": resolution_result.resolution,
                "resolution_path": "manual_fallback",
                "resolution": resolution_result.resolution,
                "resolved_at": datetime.now(UTC).isoformat(),
                "resolved_by": resolved_by,
                "beneficiary_address": resolution_result.beneficiary_address,
                "gross_payout_wei": getattr(
                    resolution_result, "gross_payout_wei", resolution_result.payout_wei
                ),
                "resolution_fee_wei": getattr(
                    resolution_result, "resolution_fee_wei", 0
                ),
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
        items.sort(
            key=lambda item: (
                str(item["event_timestamp"]),
                _CHALLENGER_EVENT_PRIORITY.get(str(item.get("event_kind")), 0),
            ),
            reverse=True,
        )
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
        snapshot = self._record_snapshot_metadata({"submission": normalized["submission"]})
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
            onchain.setdefault("snapshot_block_number", snapshot["snapshot_block_number"])
            onchain.setdefault("snapshot_block_hash", snapshot["snapshot_block_hash"])
            onchain.setdefault(
                "target_code_hash_at_snapshot",
                snapshot["target_code_hash_at_snapshot"],
            )
            onchain.setdefault("proxy_kind", snapshot["proxy_kind"])
            onchain.setdefault(
                "proxy_resolution_status", snapshot["proxy_resolution_status"]
            )
            onchain.setdefault(
                "proxy_resolution_detail", snapshot["proxy_resolution_detail"]
            )
            onchain.setdefault(
                "implementation_address_at_snapshot",
                snapshot["implementation_address_at_snapshot"],
            )
            onchain.setdefault(
                "implementation_code_hash_at_snapshot",
                snapshot["implementation_code_hash_at_snapshot"],
            )
            onchain["challenge_policy"] = self._normalize_challenge_policy(
                onchain.get("challenge_policy")
            )
            request_claim_id = onchain.get("request_claim_id")
            if self.publisher is not None and request_claim_id is not None:
                try:
                    onchain_claim = self.publisher.get_audit_request_claim(int(request_claim_id))
                except Exception:
                    onchain_claim = None
                else:
                    onchain["claim_state"] = onchain_claim.state
                    onchain["published_at"] = self._isoformat_unix_timestamp(
                        onchain_claim.submitted_at
                    )
                    onchain["stake_wei"] = onchain_claim.stake_wei
                    onchain["agent_id"] = onchain_claim.agent_id
                    onchain["agent_registry"] = onchain_claim.agent_registry.lower()
                    onchain["auditor_address"] = onchain_claim.auditor_address.lower()
            normalized["onchain"] = onchain
        challenge = normalized.get("challenge")
        if isinstance(challenge, dict):
            normalized["challenge"] = self._normalize_challenge(
                challenge,
                audit_id=str(normalized.get("id") or ""),
            )
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
                reputation["policy_openness_score_total"] = int(
                    reputation.get("policy_openness_score_total") or 0
                )
                reputation["policy_openness_score_total"] += self._challenge_policy_openness_score(
                    self._challenge_policy_for_record(record)
                )
            if status == "challenged":
                reputation["open_challenge_count"] += 1
            challenge = record.get("challenge")
            if isinstance(challenge, dict) and not self._challenge_is_admissible(challenge):
                reputation["inadmissible_challenge_count"] += 1
            if status == "resolved" and isinstance(challenge, dict):
                reputation["resolved_challenge_count"] += 1
                resolution = str(challenge.get("resolution") or "")
                if resolution == "rejected":
                    reputation["challenge_rejected_count"] += 1
                elif resolution == "upheld":
                    reputation["challenge_upheld_count"] += 1
                if self._challenge_is_admissible(challenge):
                    reputation["admissible_resolved_challenge_count"] += 1
                    if resolution == "rejected":
                        reputation["admissible_challenge_rejected_count"] += 1
                    elif resolution == "upheld":
                        reputation["admissible_challenge_upheld_count"] += 1
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
            published_claim_count = int(reputation["published_claim_count"])
            admissible_resolved_count = int(reputation["admissible_resolved_challenge_count"])
            openness_total = int(reputation.pop("policy_openness_score_total", 0))
            if published_claim_count == 0:
                reputation["challenge_openness_score"] = 50
                reputation["challenge_openness_band"] = "provisional"
                reputation["policy_openness_weight"] = 0.5
            else:
                openness_score = round(openness_total / published_claim_count)
                reputation["challenge_openness_score"] = openness_score
                reputation["challenge_openness_band"] = self._challenge_openness_band(
                    openness_score
                )
                reputation["policy_openness_weight"] = round(openness_score / 100, 2)

            if admissible_resolved_count == 0:
                reputation["challenge_accuracy_score"] = 50
                reputation["challenge_accuracy_band"] = "provisional"
            else:
                accuracy_score = round(
                    100
                    * int(reputation["admissible_challenge_rejected_count"])
                    / admissible_resolved_count
                )
                reputation["challenge_accuracy_score"] = accuracy_score
                reputation["challenge_accuracy_band"] = self._challenge_accuracy_band(
                    accuracy_score
                )

            if published_claim_count == 0 and admissible_resolved_count == 0:
                reputation["score"] = 50
                reputation["band"] = "provisional"
            else:
                reputation["score"] = round(
                    (0.35 * int(reputation["challenge_openness_score"]))
                    + (0.65 * int(reputation["challenge_accuracy_score"]))
                )
                reputation["band"] = self._aggregate_reputation_band(reputation["score"])
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
            "challenge_openness_score": 50,
            "challenge_openness_band": "provisional",
            "challenge_accuracy_score": 50,
            "challenge_accuracy_band": "provisional",
            "policy_openness_weight": 0.5,
            "resolved_challenge_count": 0,
            "challenge_rejected_count": 0,
            "challenge_upheld_count": 0,
            "admissible_resolved_challenge_count": 0,
            "admissible_challenge_rejected_count": 0,
            "admissible_challenge_upheld_count": 0,
            "inadmissible_challenge_count": 0,
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
                "Neutral 50 when there are no published claims and no admissible resolved "
                "challenges; otherwise round(0.35 * challenge_openness_score + "
                "0.65 * challenge_accuracy_score)."
            ),
            "challenge_openness_formula": (
                "Neutral 50 when there are no published claims; otherwise average the "
                "per-claim policy openness score derived from evidence coverage, severity "
                "threshold, informational scope, material-incorrectness requirement, and "
                "strict vs broad admissibility."
            ),
            "challenge_accuracy_formula": (
                "Neutral 50 when there are no admissible resolved challenges; otherwise "
                "round(100 * admissible_challenge_rejected_count / "
                "admissible_resolved_challenge_count). Inadmissible challenges are excluded."
            ),
        }

    def _challenge_policy_openness_score(self, policy: dict[str, Any] | None) -> int:
        normalized = self._normalize_challenge_policy(policy)
        evidence_points = round(
            35 * (len(normalized["allowed_evidence_types"]) / 2)
        )
        severity_points = _POLICY_OPENNESS_THRESHOLD_POINTS[
            str(normalized["min_severity_threshold"])
        ]
        informational_points = 10 if normalized["allow_informational_only"] else 0
        material_points = 10 if not normalized["requires_material_incorrectness"] else 0
        mode_points = 15 if normalized["admissibility_mode"] == "broad" else 6
        return int(
            evidence_points
            + severity_points
            + informational_points
            + material_points
            + mode_points
        )

    def _challenge_is_admissible(self, challenge: dict[str, Any]) -> bool:
        policy_status = str(challenge.get("policy_admissibility_status") or "").strip()
        if policy_status == "admissible":
            return True
        if policy_status.startswith("inadmissible_"):
            return False
        verification_status = str(challenge.get("verification_status") or "").strip()
        return not verification_status.startswith("inadmissible_")

    def _challenge_openness_band(self, score: int) -> str:
        if score >= 75:
            return "open"
        if score >= 45:
            return "balanced"
        return "restrictive"

    def _challenge_accuracy_band(self, score: int) -> str:
        if score >= 75:
            return "strong"
        if score >= 40:
            return "mixed"
        return "weak"

    def _aggregate_reputation_band(self, score: int) -> str:
        if score >= 75:
            return "trusted"
        if score >= 40:
            return "mixed"
        return "contested"

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
            "verification_status": challenge.get("verification_status"),
            "verification_dossier_path": (
                f"/audits/{record['id']}/challenge/dossier"
                if isinstance(challenge.get("verification_dossier"), dict)
                else None
            ),
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

    def _isoformat_unix_timestamp(self, timestamp: int) -> str:
        return datetime.fromtimestamp(int(timestamp), UTC).isoformat()

    def _next_created_at_isoformat(self) -> str:
        candidate = datetime.now(UTC)
        if self._last_created_at is not None and candidate <= self._last_created_at:
            candidate = self._last_created_at + timedelta(microseconds=1)
        self._last_created_at = candidate
        return candidate.isoformat()

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
        return f"{self._public_api_base_url()}/audits/{audit_id}/reputation/claim"

    def _reputation_resolution_uri(self, audit_id: str) -> str:
        return f"{self._public_api_base_url()}/audits/{audit_id}/reputation/resolution"

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
                "snapshotBlockNumber": onchain.get("snapshot_block_number"),
                "snapshotBlockHash": onchain.get("snapshot_block_hash"),
                "targetCodeHashAtSnapshot": onchain.get("target_code_hash_at_snapshot"),
                "proxyKind": onchain.get("proxy_kind"),
                "proxyResolutionStatus": onchain.get("proxy_resolution_status"),
                "proxyResolutionDetail": onchain.get("proxy_resolution_detail"),
                "implementationAddressAtSnapshot": onchain.get(
                    "implementation_address_at_snapshot"
                ),
                "implementationCodeHashAtSnapshot": onchain.get(
                    "implementation_code_hash_at_snapshot"
                ),
                "challengePolicy": self._challenge_policy_for_record(record),
            },
            "service": {
                "registrationUri": service.get("registration_uri"),
                "registrationEndpoint": (
                    f"{self._public_api_base_url()}"
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
        return f"{self._public_api_base_url()}/audits/{audit_id}/validation/request"

    def _validation_response_uri(self, audit_id: str) -> str:
        return f"{self._public_api_base_url()}/audits/{audit_id}/validation/response"

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
                "snapshotBlockNumber": onchain.get("snapshot_block_number"),
                "snapshotBlockHash": onchain.get("snapshot_block_hash"),
                "targetCodeHashAtSnapshot": onchain.get("target_code_hash_at_snapshot"),
                "proxyKind": onchain.get("proxy_kind"),
                "proxyResolutionStatus": onchain.get("proxy_resolution_status"),
                "proxyResolutionDetail": onchain.get("proxy_resolution_detail"),
                "implementationAddressAtSnapshot": onchain.get(
                    "implementation_address_at_snapshot"
                ),
                "implementationCodeHashAtSnapshot": onchain.get(
                    "implementation_code_hash_at_snapshot"
                ),
                "challengePolicy": self._challenge_policy_for_record(record),
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
                    f"{self._public_api_base_url()}"
                    f"{service.get('registration_endpoint') or '/auditor/registration'}"
                ),
            },
        }

    def _public_api_base_url(self) -> str:
        return (
            self.contract_config.public_api_base_url()
            or self.contract_config.runtime_api_base_url
        )

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

    def _normalize_challenge(
        self, challenge: Any, *, audit_id: str | None = None
    ) -> dict[str, Any]:
        payload = deepcopy(challenge) if isinstance(challenge, dict) else {}
        payload["evidence_type"] = str(
            payload.get("evidence_type") or "deterministic_fixture"
        )
        payload["policy_admissibility_status"] = (
            str(payload.get("policy_admissibility_status"))
            if payload.get("policy_admissibility_status") is not None
            else None
        )
        payload["policy_admissibility_rationale"] = (
            str(payload.get("policy_admissibility_rationale"))
            if payload.get("policy_admissibility_rationale") is not None
            else None
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
        payload["verification_dossier_path"] = (
            str(payload.get("verification_dossier_path"))
            if payload.get("verification_dossier_path") is not None
            else (
                f"/audits/{audit_id}/challenge/dossier"
                if audit_id and payload.get("verification_dossier") is not None
                else None
            )
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

    def get_challenge_verification_dossier(self, audit_id: str) -> dict[str, Any] | None:
        record = self.get_audit(audit_id)
        if record is None:
            return None
        challenge = record.get("challenge")
        if not isinstance(challenge, dict):
            return None
        dossier = challenge.get("verification_dossier")
        if not isinstance(dossier, dict):
            return None
        return deepcopy(dossier)

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
                "network",
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
            "admissibility_status": (
                str(policy.get("admissibility_status"))
                if policy.get("admissibility_status") is not None
                else None
            ),
            "effective_policy": self._normalize_challenge_policy(
                policy.get("effective_policy")
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
        snapshot_block_number = (
            int(submission["snapshot_block_number"])
            if submission.get("snapshot_block_number") is not None
            else None
        )
        snapshot_block_hash = (
            str(submission["snapshot_block_hash"])
            if submission.get("snapshot_block_hash") is not None
            else None
        )
        target_code_hash_at_snapshot = (
            str(submission["target_code_hash_at_snapshot"])
            if submission.get("target_code_hash_at_snapshot") is not None
            else None
        )
        proxy_kind = (
            str(submission["proxy_kind"])
            if submission.get("proxy_kind") is not None
            else None
        )
        proxy_resolution_status = (
            str(submission["proxy_resolution_status"])
            if submission.get("proxy_resolution_status") is not None
            else None
        )
        proxy_resolution_detail = (
            str(submission["proxy_resolution_detail"])
            if submission.get("proxy_resolution_detail") is not None
            else None
        )
        implementation_address_at_snapshot = (
            str(submission["implementation_address_at_snapshot"])
            if submission.get("implementation_address_at_snapshot") is not None
            else None
        )
        implementation_code_hash_at_snapshot = (
            str(submission["implementation_code_hash_at_snapshot"])
            if submission.get("implementation_code_hash_at_snapshot") is not None
            else None
        )

        if input_kind == "demo_fixture":
            fixture = self.worker.require_fixture(fixture_id)
            return {
                "input_kind": "demo_fixture",
                "service_id": service_id,
                "network": self.contract_config.network,
                "chain_id": chain_id or self.contract_config.chain_id,
                "contract_address": fixture.address,
                "fixture_id": fixture.fixture_id,
                "entry_contract": entry_contract or fixture.entry_contract,
                "source_bundle_uri": source_bundle_uri,
                "source_bundle_label": source_bundle_label or fixture.label,
                "repository_url": repository_url,
                "snapshot_block_number": snapshot_block_number,
                "snapshot_block_hash": snapshot_block_hash,
                "target_code_hash_at_snapshot": target_code_hash_at_snapshot,
                "proxy_kind": proxy_kind,
                "proxy_resolution_status": proxy_resolution_status,
                "proxy_resolution_detail": proxy_resolution_detail,
                "implementation_address_at_snapshot": implementation_address_at_snapshot,
                "implementation_code_hash_at_snapshot": implementation_code_hash_at_snapshot,
            }

        if input_kind == "source_bundle":
            if not source_bundle_uri:
                raise ValueError("source_bundle_uri is required for source_bundle submissions")
            return {
                "input_kind": "source_bundle",
                "service_id": service_id,
                "network": self.contract_config.network,
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
                "snapshot_block_number": snapshot_block_number,
                "snapshot_block_hash": snapshot_block_hash,
                "target_code_hash_at_snapshot": target_code_hash_at_snapshot,
                "proxy_kind": proxy_kind,
                "proxy_resolution_status": proxy_resolution_status,
                "proxy_resolution_detail": proxy_resolution_detail,
                "implementation_address_at_snapshot": implementation_address_at_snapshot,
                "implementation_code_hash_at_snapshot": implementation_code_hash_at_snapshot,
            }

        if input_kind == "repository_url":
            if not repository_url:
                raise ValueError("repository_url is required for repository_url submissions")
            return {
                "input_kind": "repository_url",
                "service_id": service_id,
                "network": self.contract_config.network,
                "chain_id": chain_id,
                "contract_address": f"0x{sha256(repository_url.encode('utf-8')).hexdigest()[:40]}",
                "fixture_id": fixture_id,
                "entry_contract": entry_contract,
                "source_bundle_uri": source_bundle_uri,
                "source_bundle_label": source_bundle_label,
                "repository_url": repository_url,
                "snapshot_block_number": snapshot_block_number,
                "snapshot_block_hash": snapshot_block_hash,
                "target_code_hash_at_snapshot": target_code_hash_at_snapshot,
                "proxy_kind": proxy_kind,
                "proxy_resolution_status": proxy_resolution_status,
                "proxy_resolution_detail": proxy_resolution_detail,
                "implementation_address_at_snapshot": implementation_address_at_snapshot,
                "implementation_code_hash_at_snapshot": implementation_code_hash_at_snapshot,
            }

        contract_address = submission.get("contract_address")
        if not contract_address:
            raise ValueError("contract_address is required for deployed_address submissions")
        return {
            "input_kind": "deployed_address",
            "service_id": service_id,
            "network": self.contract_config.network,
            "chain_id": chain_id or self.contract_config.chain_id,
            "contract_address": str(contract_address).strip().lower(),
            "fixture_id": fixture_id,
            "entry_contract": entry_contract,
            "source_bundle_uri": source_bundle_uri,
            "source_bundle_label": source_bundle_label,
            "repository_url": repository_url,
            "snapshot_block_number": snapshot_block_number,
            "snapshot_block_hash": snapshot_block_hash,
            "target_code_hash_at_snapshot": target_code_hash_at_snapshot,
            "proxy_kind": proxy_kind,
            "proxy_resolution_status": proxy_resolution_status,
            "proxy_resolution_detail": proxy_resolution_detail,
            "implementation_address_at_snapshot": implementation_address_at_snapshot,
            "implementation_code_hash_at_snapshot": implementation_code_hash_at_snapshot,
        }

    def _normalize_target_key(self, contract_address: str | None) -> str:
        if not contract_address:
            raise ValueError("contract_address is required to derive a target key")
        return str(contract_address).strip().lower()

    def _target_auditor_key(self, target_key: str, auditor_id: str) -> str:
        return f"{target_key}::{auditor_id.strip()}"
