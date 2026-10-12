from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch
from uuid import uuid4

from eth_abi import encode
import httpx
import pytest
from web3 import Web3

from proof_of_audit_api.config import DEFAULT_DEPLOYMENTS_DIR, load_json_file
from proof_of_audit_api.security import API_KEY_HEADER_NAME
from helpers import build_onchain_test_context
from testnet.conftest import (
    TestnetContext as _TestnetContext,
    _build_testnet_client,
    assert_base_sepolia_manifest_matches_api,
)


@pytest.fixture(scope="module")
def lifecycle_context() -> tuple[_TestnetContext, str]:
    onchain = build_onchain_test_context()
    web3 = onchain.web3
    contract = onchain.contract
    target_address = web3.eth.accounts[7]
    stake_wei = int(onchain.contract_config.required_stake_wei)
    bond_wei = int(onchain.contract_config.required_challenge_bond_wei)

    published = onchain.publisher.publish_audit(
        target_address=target_address,
        report_hash="0x" + "11" * 32,
        metadata_hash="0x" + "22" * 32,
        max_severity=0,
        finding_count=0,
        stake_wei=stake_wei,
    )
    challenged = onchain.secondary_publisher.challenge_audit(
        audit_id=published.audit_id,
        evidence_hash="0x" + "33" * 32,
        challenge_bond_wei=bond_wei,
    )
    resolved = onchain.arbiter_client.resolve_challenge(
        audit_id=published.audit_id,
        upheld=True,
    )

    audit_id = f"local-evidence-{uuid4().hex}"
    context = _TestnetContext(
        api_url="",
        rpc_url="",
        chain_id=int(web3.eth.chain_id),
        private_key="unused-local-test-key",
        client=Mock(),  # type: ignore[arg-type]
        web3=web3,
        contract=contract,
        config={},
        auditor={},
        fixtures=[],
        smoke_fixture={},
        verified_addresses={},
    )
    context.audit_artifacts[audit_id] = {
        "audit_id": audit_id,
        "contract_address": target_address,
        "settlement_contract_address": contract.address,
        "chain_id": int(web3.eth.chain_id),
        "published_audit_id": published.audit_id,
        "publish_tx_hash": published.tx_hash,
        "challenge_tx_hash": challenged.tx_hash,
        "resolve_tx_hash": resolved.tx_hash,
    }
    return context, audit_id


def test_lifecycle_evidence_records_real_payout_from_successful_receipts(
    lifecycle_context: tuple[_TestnetContext, str],
) -> None:
    context, audit_id = lifecycle_context
    context.record_lifecycle_evidence(audit_id)

    evidence = context.audit_artifacts[audit_id]["lifecycle_evidence"]
    final_record = context.contract.functions.getAudit(
        evidence["published_audit_id"]
    ).call()
    expected_payout = int(final_record[6]) + int(final_record[7])

    assert evidence["chain_id"] == context.chain_id
    assert evidence["settlement_contract_address"] == context.contract.address
    assert evidence["receipts"].keys() == {"publish", "challenge", "resolve"}
    assert all(receipt["status"] == 1 for receipt in evidence["receipts"].values())
    assert evidence["stake_wei"] == int(final_record[6]) > 0
    assert evidence["bond_wei"] == int(final_record[7]) > 0
    assert evidence["payout"] == {
        "tx_hash": context.audit_artifacts[audit_id]["resolve_tx_hash"],
        "beneficiary": Web3.to_checksum_address(final_record[12]),
        "amount_wei": expected_payout,
        "resolution": 1,
    }


def test_record_gas_and_lifecycle_reject_reverted_receipt(
    lifecycle_context: tuple[_TestnetContext, str],
) -> None:
    context, audit_id = lifecycle_context
    challenge_hash = context.audit_artifacts[audit_id]["challenge_tx_hash"]
    original_get_receipt = context.web3.eth.get_transaction_receipt

    def reverted_receipt(tx_hash: Any) -> Any:
        receipt = original_get_receipt(tx_hash)
        if Web3.to_hex(receipt["transactionHash"]).casefold() == challenge_hash.casefold():
            result = dict(receipt)
            result["status"] = 0
            return result
        return receipt

    with patch.object(
        context.web3.eth, "get_transaction_receipt", side_effect=reverted_receipt
    ):
        with pytest.raises(AssertionError, match="reverted"):
            context.record_gas("challenge", challenge_hash)
        with pytest.raises(AssertionError, match="reverted"):
            context.record_lifecycle_evidence(audit_id)


def test_lifecycle_evidence_rejects_wrong_transaction_target(
    lifecycle_context: tuple[_TestnetContext, str],
) -> None:
    context, audit_id = lifecycle_context
    challenge_hash = context.audit_artifacts[audit_id]["challenge_tx_hash"]
    original_get_transaction = context.web3.eth.get_transaction

    def wrong_target(tx_hash: Any) -> Any:
        transaction = original_get_transaction(tx_hash)
        if Web3.to_hex(transaction["hash"]).casefold() == challenge_hash.casefold():
            result = dict(transaction)
            result["to"] = context.web3.eth.accounts[8]
            return result
        return transaction

    with patch.object(context.web3.eth, "get_transaction", side_effect=wrong_target):
        with pytest.raises(AssertionError, match="did not target"):
            context.record_lifecycle_evidence(audit_id)


def test_lifecycle_evidence_rejects_events_for_a_different_audit_id(
    lifecycle_context: tuple[_TestnetContext, str],
) -> None:
    context, audit_id = lifecycle_context
    artifact = context.audit_artifacts[audit_id]
    original_audit_id = artifact["published_audit_id"]
    artifact["published_audit_id"] = original_audit_id + 1
    try:
        with pytest.raises(AssertionError, match="expected one AuditPublished"):
            context.record_lifecycle_evidence(audit_id)
    finally:
        artifact["published_audit_id"] = original_audit_id


def test_lifecycle_evidence_rejects_wrong_resolution_payout(
    lifecycle_context: tuple[_TestnetContext, str],
) -> None:
    context, audit_id = lifecycle_context
    artifact = context.audit_artifacts[audit_id]
    resolve_hash = artifact["resolve_tx_hash"]
    expected_payout = int(
        context.contract.functions.getAudit(artifact["published_audit_id"]).call()[6]
    ) + int(context.contract.functions.getAudit(artifact["published_audit_id"]).call()[7])
    original_get_receipt = context.web3.eth.get_transaction_receipt
    resolution_topic = Web3.keccak(
        text="ChallengeResolved(uint256,uint8,address,uint256)"
    )

    def wrong_payout_receipt(tx_hash: Any) -> Any:
        receipt = original_get_receipt(tx_hash)
        if Web3.to_hex(receipt["transactionHash"]).casefold() != resolve_hash.casefold():
            return receipt
        result = dict(receipt)
        logs = [dict(log) for log in receipt["logs"]]
        event_found = False
        for log in logs:
            if log["topics"][0] == resolution_topic:
                log["data"] = encode(["uint8", "uint256"], [1, expected_payout - 1])
                event_found = True
        assert event_found, "local resolve receipt has no ChallengeResolved event"
        result["logs"] = logs
        return result

    with patch.object(
        context.web3.eth, "get_transaction_receipt", side_effect=wrong_payout_receipt
    ):
        with pytest.raises(AssertionError, match="payout does not equal"):
            context.record_lifecycle_evidence(audit_id)


def test_manifest_preflight_accepts_current_address_case_insensitively() -> None:
    manifest_file = DEFAULT_DEPLOYMENTS_DIR / "base-sepolia.json"
    manifest = load_json_file(manifest_file)
    address = str(manifest["address"])

    assert_base_sepolia_manifest_matches_api(
        {
            "chain_id": manifest["chain_id"],
            "contract_address": address.upper(),
        },
        manifest_file=manifest_file,
    )


def test_manifest_preflight_rejects_wrong_api_address(tmp_path: Path) -> None:
    manifest_file = tmp_path / "base-sepolia.json"
    manifest_file.write_text(
        json.dumps({"chain_id": 84532, "address": "0x" + "11" * 20}),
        encoding="utf-8",
    )

    with pytest.raises(AssertionError, match="does not match"):
        assert_base_sepolia_manifest_matches_api(
            {"chain_id": 84532, "contract_address": "0x" + "22" * 20},
            manifest_file=manifest_file,
        )


def test_manifest_preflight_rejects_absent_manifest_address(tmp_path: Path) -> None:
    manifest_file = tmp_path / "base-sepolia.json"
    manifest_file.write_text(json.dumps({"chain_id": 84532}), encoding="utf-8")

    with pytest.raises(AssertionError, match="has no address"):
        assert_base_sepolia_manifest_matches_api(
            {"chain_id": 84532, "contract_address": "0x" + "22" * 20},
            manifest_file=manifest_file,
        )


def test_manifest_preflight_rejects_chain_id_mismatch(tmp_path: Path) -> None:
    manifest_file = tmp_path / "base-sepolia.json"
    manifest_file.write_text(
        json.dumps({"chain_id": 84531, "address": "0x" + "11" * 20}),
        encoding="utf-8",
    )

    with pytest.raises(AssertionError, match="does not match API chain id"):
        assert_base_sepolia_manifest_matches_api(
            {"chain_id": 84532, "contract_address": "0x" + "11" * 20},
            manifest_file=manifest_file,
        )


def test_testnet_client_sends_trimmed_api_key_on_mock_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PROOF_OF_AUDIT_TESTNET_API_KEY", "  smoke-token-value \t")
    requests: list[tuple[str, str | None]] = []

    def handle_request(request: httpx.Request) -> httpx.Response:
        requests.append((request.url.path, request.headers.get(API_KEY_HEADER_NAME)))
        return httpx.Response(200, json={"status": "ok"})

    with _build_testnet_client(
        "https://smoke.example", transport=httpx.MockTransport(handle_request)
    ) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/config").status_code == 200
        assert client.follow_redirects is False

    assert requests == [
        ("/health", "smoke-token-value"),
        ("/config", "smoke-token-value"),
    ]


def test_testnet_client_stops_redirects_when_api_key_is_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PROOF_OF_AUDIT_TESTNET_API_KEY", "smoke-token-value")
    requests: list[tuple[str, str | None]] = []

    def handle_request(request: httpx.Request) -> httpx.Response:
        requests.append((request.url.host, request.headers.get(API_KEY_HEADER_NAME)))
        return httpx.Response(
            302,
            headers={"Location": "https://other-origin.example/redirected"},
        )

    with _build_testnet_client(
        "https://smoke.example", transport=httpx.MockTransport(handle_request)
    ) as client:
        response = client.get("/redirect")

    assert response.status_code == 302
    assert response.history == []
    assert requests == [("smoke.example", "smoke-token-value")]


def test_testnet_client_keeps_redirects_when_api_key_is_unset_or_blank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[tuple[str, str | None]] = []

    def handle_request(request: httpx.Request) -> httpx.Response:
        requests.append((request.url.path, request.headers.get(API_KEY_HEADER_NAME)))
        if request.url.path == "/redirect":
            return httpx.Response(302, headers={"Location": "/health"})
        return httpx.Response(200, json={"status": "ok"})

    for value in (None, "", " \t "):
        if value is None:
            monkeypatch.delenv("PROOF_OF_AUDIT_TESTNET_API_KEY", raising=False)
        else:
            monkeypatch.setenv("PROOF_OF_AUDIT_TESTNET_API_KEY", value)
        with _build_testnet_client(
            "https://smoke.example", transport=httpx.MockTransport(handle_request)
        ) as client:
            response = client.get("/redirect")
            assert client.follow_redirects is True
            assert response.status_code == 200
            assert len(response.history) == 1

    assert requests == [
        ("/redirect", None),
        ("/health", None),
        ("/redirect", None),
        ("/health", None),
        ("/redirect", None),
        ("/health", None),
    ]
