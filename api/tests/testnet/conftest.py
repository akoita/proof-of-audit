from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pytest
from web3 import HTTPProvider, Web3
from web3.contract import Contract
from web3.logs import DISCARD

from proof_of_audit_api.config import DEFAULT_DEPLOYMENTS_DIR, load_json_file
from proof_of_audit_api.publisher import load_contract_abi


ROOT_DIR = Path(__file__).resolve().parents[3]


@dataclass
class GasMeasurement:
    action: str
    tx_hash: str
    gas_used: int
    block_number: int
    status: int


@dataclass
class TestnetContext:
    api_url: str
    rpc_url: str
    chain_id: int
    private_key: str
    client: httpx.Client
    web3: Web3
    contract: Contract
    config: dict[str, Any]
    auditor: dict[str, Any]
    fixtures: list[dict[str, Any]]
    smoke_fixture: dict[str, Any]
    verified_addresses: dict[str, str]
    gas_measurements: list[GasMeasurement] = field(default_factory=list)
    audit_artifacts: dict[str, dict[str, Any]] = field(default_factory=dict)
    failed_submissions: list[dict[str, Any]] = field(default_factory=list)

    @property
    def operator_address(self) -> str:
        return self.web3.eth.account.from_key(self.private_key).address

    def create_audit(
        self,
        *,
        contract_address: str | None = None,
        input_kind: str = "deployed_address",
        fixture_id: str | None = None,
        entry_contract: str | None = None,
        source_bundle_uri: str | None = None,
        source_bundle_label: str | None = None,
        repository_url: str | None = None,
        submitted_by: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "input_kind": input_kind,
            "submitted_by": submitted_by or f"testnet-smoke-{uuid4().hex[:8]}",
        }
        if contract_address is not None:
            payload["contract_address"] = contract_address
        if fixture_id is not None:
            payload["fixture_id"] = fixture_id
        if entry_contract is not None:
            payload["entry_contract"] = entry_contract
        if source_bundle_uri is not None:
            payload["source_bundle_uri"] = source_bundle_uri
        if source_bundle_label is not None:
            payload["source_bundle_label"] = source_bundle_label
        if repository_url is not None:
            payload["repository_url"] = repository_url
        response = self.client.post("/audits", json=payload)
        assert response.status_code == 201, response.text
        created = response.json()
        self._update_audit_artifact(
            created,
            extra={
                "input_kind": payload["input_kind"],
                "fixture_id": payload.get("fixture_id"),
                "entry_contract": payload.get("entry_contract"),
                "source_bundle_uri": payload.get("source_bundle_uri"),
                "source_bundle_label": payload.get("source_bundle_label"),
                "repository_url": payload.get("repository_url"),
            },
        )
        return created

    def publish_audit(self, audit_id: str, *, stake_wei: int | None = None) -> dict[str, Any]:
        response = self.client.post(
            f"/audits/{audit_id}/publish",
            json={"stake_wei": stake_wei or self.config["required_stake_wei"]},
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        tx_hash = payload.get("onchain", {}).get("publish_tx_hash")
        self._update_audit_artifact(payload)
        if isinstance(tx_hash, str) and tx_hash:
            self.record_gas("publish", tx_hash)
        return payload

    def challenge_audit(
        self,
        audit_id: str,
        proof_uri: str,
        *,
        challenger: str = "testnet-smoke",
        evidence_type: str = "deterministic_fixture",
        execution_env: str | None = None,
        evidence_manifest: dict[str, Any] | None = None,
        gas_action: str = "challenge",
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "proof_uri": proof_uri,
            "challenger": challenger,
            "evidence_type": evidence_type,
        }
        if execution_env is not None:
            payload["execution_env"] = execution_env
        if evidence_manifest is not None:
            payload["evidence_manifest"] = evidence_manifest
        response = self.client.post(f"/audits/{audit_id}/challenge", json=payload)
        assert response.status_code == 200, response.text
        result = response.json()
        tx_hash = result.get("challenge", {}).get("challenge_tx_hash")
        self._update_audit_artifact(result)
        resolve_tx = result.get("challenge", {}).get("resolve_tx_hash")
        if isinstance(tx_hash, str) and tx_hash:
            self.record_gas(gas_action, tx_hash)
        if isinstance(resolve_tx, str) and resolve_tx:
            self.record_gas(f"{gas_action}_resolve", resolve_tx)
        return result

    def resolve_audit(
        self,
        audit_id: str,
        *,
        upheld: bool,
        resolved_by: str = "testnet-smoke-arbiter",
    ) -> dict[str, Any]:
        response = self.client.post(
            f"/audits/{audit_id}/resolve",
            json={"upheld": upheld, "resolved_by": resolved_by},
        )
        assert response.status_code == 200, response.text
        result = response.json()
        tx_hash = result.get("challenge", {}).get("resolve_tx_hash")
        self._update_audit_artifact(result)
        if isinstance(tx_hash, str) and tx_hash:
            self.record_gas("manual_resolve", tx_hash)
        return result

    def get_audit(self, audit_id: str) -> dict[str, Any]:
        response = self.client.get(f"/audits/{audit_id}")
        assert response.status_code == 200, response.text
        payload = response.json()
        self._update_audit_artifact(payload)
        return payload

    def record_gas(self, action: str, tx_hash: str) -> None:
        receipt = self.web3.eth.get_transaction_receipt(tx_hash)
        assert int(receipt["status"]) == 1, f"{action} transaction reverted: {tx_hash}"
        self.gas_measurements.append(
            GasMeasurement(
                action=action,
                tx_hash=tx_hash,
                gas_used=int(receipt["gasUsed"]),
                block_number=int(receipt["blockNumber"]),
                status=int(receipt["status"]),
            )
        )

    def record_lifecycle_evidence(self, audit_id: str) -> None:
        """Validate and store receipt evidence for an upheld challenge lifecycle."""
        artifact = self.audit_artifacts.get(audit_id)
        assert isinstance(artifact, dict), f"audit artifact is missing for {audit_id}"

        settlement_address = _normalized_address(
            self.web3, self.contract.address, "context settlement address"
        )
        artifact_settlement = _normalized_address(
            self.web3,
            artifact.get("settlement_contract_address"),
            "artifact settlement address",
        )
        assert artifact_settlement == settlement_address, (
            "artifact settlement address does not match the configured contract"
        )

        published_audit_id = artifact.get("published_audit_id")
        assert isinstance(published_audit_id, int) and published_audit_id > 0, (
            "artifact is missing its published on-chain audit id"
        )
        assert int(self.chain_id) == int(artifact.get("chain_id") or 0), (
            "artifact chain id does not match the testnet context"
        )

        target_address = artifact.get("contract_address")
        normalized_target = _normalized_address(
            self.web3, target_address, "artifact audited contract address"
        )
        tx_hashes: dict[str, str] = {}
        receipts: dict[str, dict[str, int | str]] = {}
        raw_receipts: dict[str, Any] = {}
        transaction_hash_fields = {
            "publish": "publish_tx_hash",
            "challenge": "challenge_tx_hash",
            "resolve": "resolve_tx_hash",
        }
        for action, field_name in transaction_hash_fields.items():
            tx_hash = artifact.get(field_name)
            assert isinstance(tx_hash, str) and tx_hash.strip(), (
                f"artifact is missing its {action} transaction hash"
            )

            receipt = self.web3.eth.get_transaction_receipt(tx_hash)
            receipt_hash = Web3.to_hex(receipt["transactionHash"])
            assert receipt_hash.casefold() == tx_hash.casefold(), (
                f"{action} receipt transaction hash does not match the artifact"
            )
            status = int(receipt["status"])
            assert status == 1, f"{action} transaction reverted: {tx_hash}"

            transaction = self.web3.eth.get_transaction(tx_hash)
            transaction_hash = Web3.to_hex(transaction["hash"])
            assert transaction_hash.casefold() == tx_hash.casefold(), (
                f"{action} transaction hash does not match the artifact"
            )
            transaction_target = _normalized_address(
                self.web3, transaction.get("to"), f"{action} transaction target"
            )
            assert transaction_target == settlement_address, (
                f"{action} transaction did not target the settlement contract"
            )

            tx_hashes[action] = receipt_hash
            raw_receipts[action] = receipt
            receipts[action] = {
                "tx_hash": receipt_hash,
                "block_number": int(receipt["blockNumber"]),
                "status": status,
            }

        published_event = _unique_audit_event(
            self.contract,
            raw_receipts["publish"],
            "AuditPublished",
            settlement_address,
            published_audit_id,
        )
        challenge_event = _unique_audit_event(
            self.contract,
            raw_receipts["challenge"],
            "ChallengeOpened",
            settlement_address,
            published_audit_id,
        )
        resolved_event = _unique_audit_event(
            self.contract,
            raw_receipts["resolve"],
            "ChallengeResolved",
            settlement_address,
            published_audit_id,
        )

        final_record = self.contract.functions.getAudit(published_audit_id).call()
        assert int(final_record[10]) == 3, "final on-chain audit state is not resolved"
        published_auditor = _normalized_address(
            self.web3, published_event["auditor"], "AuditPublished auditor"
        )
        final_auditor = _normalized_address(
            self.web3, final_record[0], "final on-chain auditor"
        )
        assert published_auditor == final_auditor, (
            "published auditor does not match the final on-chain audit record"
        )
        published_target = _normalized_address(
            self.web3, published_event["target"], "AuditPublished target"
        )
        assert published_target == normalized_target, (
            "published target does not match the audit artifact"
        )

        challenger = _normalized_address(
            self.web3, challenge_event["challenger"], "ChallengeOpened challenger"
        )
        final_challenger = _normalized_address(
            self.web3, final_record[12], "final on-chain challenger"
        )
        assert challenger == final_challenger, (
            "challenger does not match the final on-chain audit record"
        )
        stake_wei = int(published_event["stakeAmount"])
        bond_wei = int(challenge_event["challengeBond"])
        assert stake_wei > 0, "published stake must be positive"
        assert bond_wei > 0, "challenge bond must be positive"
        assert int(final_record[6]) == stake_wei, (
            "published event stake does not match the final on-chain audit record"
        )
        assert int(final_record[7]) == bond_wei, (
            "challenge event bond does not match the final on-chain audit record"
        )
        assert final_record[13] == challenge_event["evidenceHash"], (
            "challenge evidence hash does not match the final on-chain audit record"
        )

        resolution = int(resolved_event["resolution"])
        beneficiary = _normalized_address(
            self.web3, resolved_event["beneficiary"], "ChallengeResolved beneficiary"
        )
        payout_wei = int(resolved_event["payout"])
        assert resolution == 1, "challenge resolution was not upheld"
        assert int(final_record[11]) == 1, "final on-chain resolution was not upheld"
        assert beneficiary == final_challenger, (
            "upheld challenge payout beneficiary does not match the challenger"
        )
        assert payout_wei == stake_wei + bond_wei, (
            "upheld challenge payout does not equal the stake plus challenge bond"
        )

        artifact["lifecycle_evidence"] = {
            "chain_id": int(self.chain_id),
            "settlement_contract_address": self.contract.address,
            "published_audit_id": published_audit_id,
            "receipts": receipts,
            "stake_wei": stake_wei,
            "bond_wei": bond_wei,
            "payout": {
                "tx_hash": tx_hashes["resolve"],
                "beneficiary": self.web3.to_checksum_address(beneficiary),
                "amount_wei": payout_wei,
                "resolution": resolution,
            },
        }

    def record_failed_submission(
        self,
        *,
        name: str,
        response: httpx.Response,
        payload: dict[str, Any],
    ) -> None:
        body: dict[str, Any]
        try:
            parsed = response.json()
            body = parsed if isinstance(parsed, dict) else {"raw": parsed}
        except ValueError:
            body = {"raw_text": response.text}
        self.failed_submissions.append(
            {
                "name": name,
                "status_code": response.status_code,
                "request_payload": payload,
                "response": body,
            }
        )

    def _update_audit_artifact(
        self, payload: dict[str, Any], *, extra: dict[str, Any] | None = None
    ) -> None:
        audit_id = payload.get("id")
        if not isinstance(audit_id, str) or not audit_id:
            return

        artifact = self.audit_artifacts.setdefault(audit_id, {"audit_id": audit_id})
        artifact["status"] = payload.get("status")
        artifact["submitted_by"] = payload.get("submitted_by")
        artifact["contract_address"] = payload.get("contract_address")

        submission = payload.get("submission")
        if isinstance(submission, dict):
            artifact["input_kind"] = submission.get("input_kind")
            artifact["fixture_id"] = submission.get("fixture_id")
            artifact["entry_contract"] = submission.get("entry_contract")
            artifact["source_bundle_uri"] = submission.get("source_bundle_uri")
            artifact["source_bundle_label"] = submission.get("source_bundle_label")
            artifact["repository_url"] = submission.get("repository_url")
            artifact["submission_contract_address"] = submission.get("contract_address")

        report = payload.get("report")
        if isinstance(report, dict):
            artifact["benchmark_id"] = report.get("benchmark_id")
            artifact["report_hash"] = report.get("report_hash")
            artifact["metadata_hash"] = report.get("metadata_hash")
            artifact["finding_count"] = report.get("finding_count")
            artifact["max_severity"] = report.get("max_severity")

        execution = payload.get("execution")
        if isinstance(execution, dict):
            artifact["execution_backend"] = execution.get("backend")
            artifact["execution_mode"] = execution.get("mode")
            artifact["execution_status"] = execution.get("status")
            artifact["execution_source"] = execution.get("source")
            artifact["execution_live_attempted"] = execution.get("live_attempted")
            artifact["execution_fallback_used"] = execution.get("fallback_used")
            artifact["execution_source_path"] = execution.get("source_path")
            artifact["execution_report_path"] = execution.get("report_path")
            artifact["execution_run_id"] = execution.get("run_id")
            artifact["execution_run_dir"] = execution.get("run_dir")
            artifact["execution_status_url"] = execution.get("status_url")
            artifact["execution_logs_url"] = execution.get("logs_url")
            artifact["execution_source_digest"] = execution.get("source_digest")
            artifact["execution_profile_id"] = execution.get("profile_id")
            artifact["execution_provider"] = execution.get("provider")
            artifact["execution_model"] = execution.get("model")
            artifact["execution_error"] = execution.get("error")

        onchain = payload.get("onchain")
        if isinstance(onchain, dict):
            artifact["published_audit_id"] = onchain.get("audit_id")
            artifact["network"] = onchain.get("network")
            artifact["chain_id"] = onchain.get("chain_id")
            artifact["settlement_contract_address"] = onchain.get("contract_address")
            artifact["publish_tx_hash"] = onchain.get("publish_tx_hash")
            artifact["publish_tx_url"] = onchain.get("publish_tx_url")

        challenge = payload.get("challenge")
        if isinstance(challenge, dict):
            artifact["challenge_status"] = challenge.get("status")
            artifact["challenge_resolution"] = challenge.get("resolution")
            artifact["resolution_path"] = challenge.get("resolution_path")
            artifact["proof_uri"] = challenge.get("proof_uri")
            artifact["evidence_type"] = challenge.get("evidence_type")
            artifact["execution_env"] = challenge.get("execution_env")
            artifact["verification_status"] = challenge.get("verification_status")
            artifact["verification_summary"] = challenge.get("verification_summary")
            artifact["challenge_hash"] = challenge.get("challenge_hash")
            artifact["challenge_tx_hash"] = challenge.get("challenge_tx_hash")
            artifact["challenge_tx_url"] = challenge.get("challenge_tx_url")
            artifact["resolve_tx_hash"] = challenge.get("resolve_tx_hash")
            artifact["resolve_tx_url"] = challenge.get("resolve_tx_url")

        if extra:
            artifact.update({key: value for key, value in extra.items() if value is not None})

def _required_env(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _checksum(web3: Web3, address: str) -> str:
    return web3.to_checksum_address(address)


def _normalized_address(web3: Web3, address: object, label: str) -> str:
    assert isinstance(address, str) and address.strip(), f"{label} is missing"
    try:
        return web3.to_checksum_address(address).casefold()
    except (TypeError, ValueError) as exc:
        raise AssertionError(f"{label} is not a valid address") from exc


def _unique_audit_event(
    contract: Contract,
    receipt: Any,
    event_name: str,
    settlement_address: str,
    published_audit_id: int,
) -> Any:
    decoded_events = getattr(contract.events, event_name)().process_receipt(
        receipt, errors=DISCARD
    )
    matches = [
        event["args"]
        for event in decoded_events
        if str(event.get("address", "")).casefold() == settlement_address
        and int(event["args"].get("auditId", -1)) == published_audit_id
    ]
    assert len(matches) == 1, (
        f"expected one {event_name} event for audit {published_audit_id} "
        f"from settlement contract, found {len(matches)}"
    )
    return matches[0]


def assert_base_sepolia_manifest_matches_api(
    config_payload: dict[str, Any], *, manifest_file: Path | None = None
) -> None:
    """Assert the API settlement address matches the configured Base Sepolia manifest."""
    if manifest_file is None:
        configured_path = _required_env("PROOF_OF_AUDIT_DEPLOYMENT_MANIFEST_FILE")
        manifest_file = (
            Path(configured_path)
            if configured_path
            else DEFAULT_DEPLOYMENTS_DIR / "base-sepolia.json"
        )

    manifest = load_json_file(manifest_file)
    manifest_address = str(manifest.get("address") or "").strip()
    assert manifest_address, (
        f"Base Sepolia deployment manifest at {manifest_file} has no address"
    )
    manifest_chain_id = manifest.get("chain_id")
    configured_chain_id = config_payload.get("chain_id")
    try:
        normalized_manifest_chain_id = int(manifest_chain_id)  # type: ignore[arg-type]
        normalized_configured_chain_id = int(configured_chain_id)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise AssertionError(
            f"Base Sepolia deployment manifest at {manifest_file} has no valid chain id"
        ) from exc
    assert normalized_manifest_chain_id == normalized_configured_chain_id, (
        f"Base Sepolia deployment manifest chain id {normalized_manifest_chain_id} "
        f"does not match API chain id {normalized_configured_chain_id}"
    )

    api_address = str(config_payload.get("contract_address") or "").strip()
    assert api_address, "API config is missing its settlement contract address"
    assert manifest_address.casefold() == api_address.casefold(), (
        "API settlement contract address does not match the Base Sepolia "
        f"deployment manifest at {manifest_file}"
    )


def _has_code(web3: Web3, address: str) -> bool:
    code = web3.eth.get_code(_checksum(web3, address))
    return bool(code and code != b"\x00")


@pytest.fixture(scope="session")
def testnet_context() -> TestnetContext:
    api_url = _required_env("PROOF_OF_AUDIT_TESTNET_API_URL")
    rpc_url = _required_env("PROOF_OF_AUDIT_TESTNET_RPC_URL")
    private_key = _required_env("PROOF_OF_AUDIT_TESTNET_PRIVATE_KEY")
    chain_id_value = _required_env("PROOF_OF_AUDIT_TESTNET_CHAIN_ID")
    missing = [
        name
        for name, value in (
            ("PROOF_OF_AUDIT_TESTNET_API_URL", api_url),
            ("PROOF_OF_AUDIT_TESTNET_RPC_URL", rpc_url),
            ("PROOF_OF_AUDIT_TESTNET_PRIVATE_KEY", private_key),
            ("PROOF_OF_AUDIT_TESTNET_CHAIN_ID", chain_id_value),
        )
        if value is None
    ]
    if missing:
        pytest.skip(f"testnet smoke env is incomplete: missing {', '.join(missing)}")

    chain_id = int(chain_id_value)
    client = httpx.Client(base_url=api_url, timeout=30.0, follow_redirects=True)
    try:
        health = client.get("/health")
        health.raise_for_status()
        config = client.get("/config")
        config.raise_for_status()
        auditor = client.get("/auditor")
        auditor.raise_for_status()
        fixtures = client.get("/fixtures")
        fixtures.raise_for_status()

        config_payload = config.json()
        auditor_payload = auditor.json()
        fixtures_payload = fixtures.json()["items"]

        web3 = Web3(HTTPProvider(rpc_url))
        if not web3.is_connected():
            pytest.skip(f"unable to reach configured RPC at {rpc_url}")
        if int(web3.eth.chain_id) != chain_id:
            pytest.skip(
                f"configured RPC chain id {web3.eth.chain_id} does not match expected {chain_id}"
            )
        if int(config_payload["chain_id"]) != chain_id:
            pytest.skip(
                f"API chain id {config_payload['chain_id']} does not match expected {chain_id}"
            )
        if str(config_payload.get("network")) != "base-sepolia":
            pytest.skip(
                f"API network {config_payload.get('network')} is not the expected base-sepolia"
            )
        assert_base_sepolia_manifest_matches_api(config_payload)

        operator = web3.eth.account.from_key(private_key).address
        if int(web3.eth.get_balance(operator)) <= 0:
            pytest.skip(
                f"configured testnet private key {operator} has no funds on chain {chain_id}"
            )

        contract_address = config_payload.get("contract_address")
        if not isinstance(contract_address, str) or not _has_code(web3, contract_address):
            pytest.skip("configured ProofOfAudit contract is missing or has no deployed code")

        verified_addresses: dict[str, str] = {"proof_of_audit": contract_address}
        for label, address in (
            ("identity_registry", auditor_payload.get("registry_contract_address")),
            ("validation_registry", auditor_payload.get("validation_registry_address")),
        ):
            if isinstance(address, str) and address:
                if not _has_code(web3, address):
                    pytest.skip(f"{label} at {address} has no deployed code")
                verified_addresses[label] = address

        smoke_fixture = next(
            (
                fixture
                for fixture in fixtures_payload
                if fixture.get("id") == "clean-vault"
                and isinstance(fixture.get("address"), str)
                and _has_code(web3, str(fixture["address"]))
                and fixture.get("challenge_proof_uri")
            ),
            None,
        )
        if smoke_fixture is None:
            pytest.skip(
                "no deployed clean-vault fixture is available on the configured Base Sepolia RPC"
            )
        verified_addresses["smoke_fixture"] = str(smoke_fixture["address"])

        contract = web3.eth.contract(
            address=_checksum(web3, contract_address),
            abi=load_contract_abi(),
        )
        context = TestnetContext(
            api_url=api_url,
            rpc_url=rpc_url,
            chain_id=chain_id,
            private_key=private_key,
            client=client,
            web3=web3,
            contract=contract,
            config=config_payload,
            auditor=auditor_payload,
            fixtures=fixtures_payload,
            smoke_fixture=smoke_fixture,
            verified_addresses=verified_addresses,
        )
        print(
            "TESTNET_CONTEXT_SUMMARY="
            + json.dumps(
                {
                    "api_url": api_url,
                    "rpc_url": rpc_url,
                    "chain_id": chain_id,
                    "operator_address": context.operator_address,
                    "verified_addresses": verified_addresses,
                    "smoke_fixture": {
                        "id": smoke_fixture.get("id"),
                        "address": smoke_fixture.get("address"),
                        "challenge_proof_uri": smoke_fixture.get("challenge_proof_uri"),
                    },
                },
                sort_keys=True,
            )
        )
        yield context
    finally:
        if "context" in locals() and context.audit_artifacts:
            summary = [
                context.audit_artifacts[audit_id]
                for audit_id in sorted(context.audit_artifacts.keys())
            ]
            print(f"TESTNET_AUDIT_ARTIFACTS={json.dumps(summary, sort_keys=True)}")
        if "context" in locals() and context.failed_submissions:
            print(
                "TESTNET_FAILURE_ARTIFACTS="
                + json.dumps(context.failed_submissions, sort_keys=True)
            )
        if "context" in locals() and context.gas_measurements:
            summary = [asdict(entry) for entry in context.gas_measurements]
            print(f"TESTNET_GAS_SUMMARY={json.dumps(summary, sort_keys=True)}")
        client.close()
