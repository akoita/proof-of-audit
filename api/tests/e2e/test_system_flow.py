from __future__ import annotations

from typing import Any

import pytest

from api.tests.e2e.conftest import SystemStack


AUDIT_STATUS_RESOLVED = 3
CHALLENGE_RESOLUTION_UPHELD = 1
CHALLENGE_RESOLUTION_REJECTED = 2


def create_audit(
    stack: SystemStack, contract_address: str, submitted_by: str = "system-e2e"
) -> dict[str, Any]:
    response = stack.client.post(
        "/audits",
        json={
            "contract_address": contract_address,
            "submitted_by": submitted_by,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def publish_audit(
    stack: SystemStack, audit_id: str, stake_wei: int | None = None
) -> dict[str, Any]:
    response = stack.client.post(
        f"/audits/{audit_id}/publish",
        json={
            "stake_wei": stake_wei or stack.config["required_stake_wei"],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def challenge_audit(
    stack: SystemStack, audit_id: str, proof_uri: str, challenger: str = "whitehat-demo"
) -> dict[str, Any]:
    response = stack.client.post(
        f"/audits/{audit_id}/challenge",
        json={
            "proof_uri": proof_uri,
            "challenger": challenger,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.system_e2e
def test_system_stack_exposes_live_contract_and_fixture_metadata(
    system_stack: SystemStack,
) -> None:
    health = system_stack.client.get("/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}

    auditor_service = system_stack.client.get("/auditor")
    assert auditor_service.status_code == 200
    assert auditor_service.json()["service_id"] == "proof-of-audit-auditor"
    assert auditor_service.json()["registration_kind"] == "offchain_manifest"
    assert auditor_service.json()["capability"] == "audit_contract"

    assert system_stack.config["deployment_ready"] is True
    assert system_stack.config["network"] == "anvil-system-e2e"
    assert system_stack.config["chain_id"] == 31339
    assert system_stack.config["auditor"]["id"] == "proof-of-audit-auditor"
    assert (
        system_stack.config["auditor_service"]["manifest_schema"]
        == "https://eips.ethereum.org/EIPS/eip-8004#registration-v1"
    )

    fixture_ids = {fixture["id"] for fixture in system_stack.fixtures}
    assert fixture_ids == {
        "vulnerable-bank",
        "admin-setter",
        "clean-vault",
        "dual-risk-vault",
        "unchecked-treasury",
    }

    for fixture in system_stack.fixtures:
        code = system_stack.web3.eth.get_code(
            system_stack.web3.to_checksum_address(fixture["address"])
        )
        assert code and code != b"\x00"


@pytest.mark.system_e2e
def test_http_publish_and_verified_challenge_rejection_resolve_onchain(
    system_stack: SystemStack,
) -> None:
    fixture = system_stack.fixture_by_id("vulnerable-bank")
    created = create_audit(system_stack, fixture["address"])
    assert created["status"] == "draft"
    assert created["agent"]["id"] == "proof-of-audit-auditor"
    assert created["report"]["benchmark_id"] == "reentrancy-bank"
    assert created["report"]["finding_count"] == 1

    published = publish_audit(system_stack, created["id"])
    assert published["status"] == "published"
    assert published["onchain"]["agent_identity"] == "proof-of-audit-auditor"
    assert published["onchain"]["chain_id"] == 31339
    assert published["onchain"]["contract_address"] == system_stack.config["contract_address"]

    challenged = challenge_audit(system_stack, created["id"], fixture["challenge_proof_uri"])
    assert challenged["status"] == "resolved"
    assert challenged["challenge"]["status"] == "rejected"
    assert challenged["challenge"]["resolution"] == "rejected"
    assert challenged["challenge"]["verification_status"] == "verified"
    assert challenged["challenge"]["resolution_path"] == "deterministic"
    assert challenged["challenge"]["resolve_tx_hash"].startswith("0x")

    fetched = system_stack.client.get(f"/audits/{created['id']}")
    assert fetched.status_code == 200
    payload = fetched.json()
    assert payload["status"] == "resolved"
    assert payload["challenge"]["status"] == "rejected"

    audit_record = system_stack.contract.functions.getAudit(payload["onchain"]["audit_id"]).call()
    assert int(audit_record[10]) == AUDIT_STATUS_RESOLVED
    assert int(audit_record[11]) == CHALLENGE_RESOLUTION_REJECTED


@pytest.mark.system_e2e
def test_invalid_evidence_requires_manual_resolution_over_http(
    system_stack: SystemStack,
) -> None:
    fixture = system_stack.fixture_by_id("clean-vault")
    created = create_audit(system_stack, fixture["address"], submitted_by="manual-review")
    publish_audit(system_stack, created["id"])

    challenged = challenge_audit(system_stack, created["id"], "ipfs://wrong-proof")
    assert challenged["status"] == "challenged"
    assert challenged["challenge"]["status"] == "opened"
    assert challenged["challenge"]["verification_status"] == "invalid_evidence"
    assert challenged["challenge"]["resolution_path"] == "manual_fallback"

    resolved = system_stack.client.post(
        f"/audits/{created['id']}/resolve",
        json={"upheld": True, "resolved_by": "arbiter-operator"},
    )
    assert resolved.status_code == 200, resolved.text
    payload = resolved.json()
    assert payload["status"] == "resolved"
    assert payload["challenge"]["status"] == "upheld"
    assert payload["challenge"]["resolution"] == "upheld"
    assert payload["challenge"]["resolve_tx_hash"].startswith("0x")

    audit_record = system_stack.contract.functions.getAudit(payload["onchain"]["audit_id"]).call()
    assert int(audit_record[10]) == AUDIT_STATUS_RESOLVED
    assert int(audit_record[11]) == CHALLENGE_RESOLUTION_UPHELD


@pytest.mark.system_e2e
def test_http_interface_rejects_duplicate_publish_and_duplicate_challenge(
    system_stack: SystemStack,
) -> None:
    fixture = system_stack.fixture_by_id("admin-setter")
    created = create_audit(system_stack, fixture["address"], submitted_by="duplicate-check")
    publish_audit(system_stack, created["id"])

    republish = system_stack.client.post(
        f"/audits/{created['id']}/publish",
        json={
            "stake_wei": system_stack.config["required_stake_wei"],
        },
    )
    assert republish.status_code == 400
    assert republish.json()["error"] == "invalid_payload"

    first_challenge = challenge_audit(system_stack, created["id"], "ipfs://wrong-proof")
    assert first_challenge["status"] == "challenged"

    second_challenge = system_stack.client.post(
        f"/audits/{created['id']}/challenge",
        json={
            "proof_uri": fixture["challenge_proof_uri"],
            "challenger": "second-whitehat",
        },
    )
    assert second_challenge.status_code == 400
    assert second_challenge.json()["error"] == "invalid_payload"


@pytest.mark.system_e2e
def test_http_interface_exposes_richer_multi_finding_reports(
    system_stack: SystemStack,
) -> None:
    fixture = system_stack.fixture_by_id("dual-risk-vault")
    created = create_audit(system_stack, fixture["address"], submitted_by="schema-check")

    report = created["report"]
    assert report["benchmark_id"] == "dual-risk-vault"
    assert report["finding_count"] == 2
    assert report["severity_breakdown"]["high"] == 1
    assert report["severity_breakdown"]["medium"] == 1
    assert [finding["category"] for finding in report["findings"]] == [
        "access_control",
        "unchecked_external_call",
    ]
    assert [finding["evidence_uri"] for finding in report["findings"]] == [
        "ipfs://dual-risk-vault/owner-takeover",
        "ipfs://dual-risk-vault/emergency-payout-failure",
    ]


@pytest.mark.system_e2e
def test_http_interface_returns_structured_errors_for_unknown_and_invalid_requests(
    system_stack: SystemStack,
) -> None:
    missing = system_stack.client.get("/audits/does-not-exist")
    assert missing.status_code == 404
    assert missing.json()["error"] == "audit_not_found"

    invalid = system_stack.client.post("/audits", json={"submitted_by": "missing-address"})
    assert invalid.status_code == 422
    assert invalid.json()["error"] == "validation_error"
