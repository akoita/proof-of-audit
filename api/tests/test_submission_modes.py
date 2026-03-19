from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from proof_of_audit_api.app import create_app


@pytest.fixture
def demo_fixtures_file(tmp_path: Path) -> Path:
    fixtures_file = tmp_path / "demo-fixtures.localhost.json"
    fixtures_file.write_text(
        json.dumps(
            {
                "fixtures": [
                    {
                        "id": "vulnerable-bank",
                        "label": "Vulnerable Bank",
                        "contract_name": "VulnerableBank",
                        "entry_contract": "VulnerableBank",
                        "benchmark_id": "reentrancy-bank",
                        "address": "0x1000000000000000000000000000000000000001",
                        "challenge_proof_uri": "ipfs://reentrancy-bank/withdraw-drain",
                        "note": "High-confidence reentrancy finding",
                        "source_path": "demo/contracts/VulnerableBank.sol",
                    },
                    {
                        "id": "dual-risk-vault",
                        "label": "Dual Risk Vault",
                        "contract_name": "DualRiskVault",
                        "entry_contract": "DualRiskVault",
                        "benchmark_id": "dual-risk-vault",
                        "address": "0x1000000000000000000000000000000000000004",
                        "challenge_proof_uri": "ipfs://dual-risk-vault/owner-takeover",
                        "note": "Multi-finding benchmark contract",
                        "source_path": "demo/contracts/DualRiskVault.sol",
                    },
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return fixtures_file


@pytest.fixture
def client(tmp_path: Path, demo_fixtures_file: Path) -> TestClient:
    env_file = tmp_path / ".env.local"
    env_file.write_text(
        f"PROOF_OF_AUDIT_DEMO_FIXTURES_FILE={demo_fixtures_file}\n",
        encoding="utf-8",
    )
    data_root = tmp_path / "data"
    data_root.mkdir()
    with TestClient(create_app(data_root, env_file=env_file)) as test_client:
        yield test_client


@pytest.fixture
def catalog_client(tmp_path: Path, demo_fixtures_file: Path) -> TestClient:
    catalog_file = tmp_path / "auditors.catalog.json"
    catalog_file.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "service": {
                            "service_id": "shadow-auditor",
                            "name": "Shadow Auditor",
                            "manifest_schema": "https://eips.ethereum.org/EIPS/eip-8004#registration-v1",
                            "manifest_hash": "shadow-manifest",
                            "registration_kind": "offchain_manifest",
                            "registration_type": "https://eips.ethereum.org/EIPS/eip-8004#registration-v1",
                            "registration_endpoint": "/auditors/shadow-auditor/registration",
                            "registration_uri": "https://example.invalid/shadow-auditor.json",
                            "agent_id": 44,
                            "agent_registry": "0x4400000000000000000000000000000000000044",
                            "identity_source": "erc8004-official",
                            "capability": "audit_contract",
                            "discovery_path": "/auditors/shadow-auditor",
                            "submit_path": "/audits",
                            "execution_mode": "local_worker",
                            "execution_endpoint": None,
                            "publish_path_template": "/audits/{id}/publish",
                            "challenge_path_template": "/audits/{id}/challenge",
                            "network": "localhost",
                            "active": True,
                            "supported_trust": ["crypto-economic"],
                            "settlement_mode": "native_proof_of_audit",
                            "publication_mode": "api_mediated",
                            "staking_adapter_kind": "native_proof_of_audit",
                            "staking_adapter_address": None,
                            "staking_adapter_method": "publishAudit",
                            "publication_scope": "submit_selected_claim",
                            "registry_contract_address": None,
                            "validation_registry_address": None,
                            "validation_source": None,
                            "validation_request_path_template": "/audits/{id}/validation/request",
                            "validation_response_path_template": "/audits/{id}/validation/response",
                            "reputation_registry_address": None,
                            "reputation_source": None,
                            "reputation_path_template": "/auditors/{id}/reputation",
                            "submission_modes": ["demo_fixture", "deployed_address", "source_bundle"],
                            "resolution_modes": ["deterministic", "manual_fallback"],
                            "deterministic_resolution_supported": True,
                            "manual_fallback_supported": True,
                        },
                        "registration_document": {
                            "type": "https://eips.ethereum.org/EIPS/eip-8004#registration-v1",
                            "name": "Shadow Auditor",
                            "description": "Secondary deterministic auditor.",
                            "image": "https://example.invalid/shadow-auditor.png",
                            "services": [
                                {
                                    "name": "registration",
                                    "endpoint": "https://example.invalid/shadow-auditor.json",
                                }
                            ],
                            "x402Support": False,
                            "active": True,
                            "registrations": [
                                {
                                    "agentId": 44,
                                    "agentRegistry": "0x4400000000000000000000000000000000000044",
                                }
                            ],
                            "supportedTrust": ["crypto-economic"],
                            "x-proof-of-audit": {
                                "id": "shadow-auditor",
                                "version": "1.2.3",
                                "serviceType": "audit_contract",
                                "capabilities": ["audit_contract"],
                                "operator": "Shadow Labs",
                                "resolutionPolicy": "deterministic-first-with-human-fallback",
                            },
                        },
                    }
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )
    env_file = tmp_path / ".env.catalog"
    env_file.write_text(
        "\n".join(
            [
                f"PROOF_OF_AUDIT_DEMO_FIXTURES_FILE={demo_fixtures_file}",
                f"PROOF_OF_AUDIT_AUDITOR_CATALOG_FILE={catalog_file}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    data_root = tmp_path / "catalog-data"
    data_root.mkdir()
    with TestClient(create_app(data_root, env_file=env_file)) as test_client:
        yield test_client


def test_create_audit_from_demo_fixture_submission(client: TestClient) -> None:
    response = client.post(
        "/audits",
        json={
            "input_kind": "demo_fixture",
            "fixture_id": "vulnerable-bank",
            "submitted_by": "fixture-test",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["agent"]["id"] == "proof-of-audit-auditor"
    assert payload["submission"]["input_kind"] == "demo_fixture"
    assert payload["submission"]["fixture_id"] == "vulnerable-bank"
    assert payload["submission"]["entry_contract"] == "VulnerableBank"
    assert payload["submission"]["source_bundle_label"] == "Vulnerable Bank"
    assert payload["contract_address"] == "0x1000000000000000000000000000000000000001"
    assert payload["report"]["benchmark_id"] == "reentrancy-bank"


def test_create_audit_from_source_bundle_inferrs_benchmark(client: TestClient) -> None:
    response = client.post(
        "/audits",
        json={
            "input_kind": "source_bundle",
            "source_bundle_uri": "ipfs://uploads/dual-risk-vault.zip",
            "source_bundle_label": "Dual Risk Vault upload",
            "entry_contract": "DualRiskVault",
            "submitted_by": "bundle-test",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["agent"]["id"] == "proof-of-audit-auditor"
    assert payload["submission"]["input_kind"] == "source_bundle"
    assert payload["submission"]["source_bundle_uri"] == "ipfs://uploads/dual-risk-vault.zip"
    assert payload["submission"]["entry_contract"] == "DualRiskVault"
    assert payload["report"]["benchmark_id"] == "dual-risk-vault"
    assert payload["report"]["contract_address"] == payload["contract_address"]
    assert payload["report"]["finding_count"] == 2


def test_source_bundle_publish_requires_real_deployment(client: TestClient) -> None:
    created = client.post(
        "/audits",
        json={
            "input_kind": "source_bundle",
            "source_bundle_uri": "ipfs://uploads/unchecked-treasury.zip",
            "entry_contract": "UncheckedTreasury",
            "submitted_by": "bundle-test",
        },
    )
    assert created.status_code == 201

    response = client.post(
        f"/audits/{created.json()['id']}/publish",
        json={"stake_wei": 10**16},
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["error"] == "invalid_payload"
    assert "must be deployed before publish" in payload["message"]


def test_repository_submission_records_fallback_execution(client: TestClient) -> None:
    response = client.post(
        "/audits",
        json={
            "input_kind": "repository_url",
            "repository_url": "https://github.com/example/vault",
            "entry_contract": "Vault",
            "submitted_by": "repo-test",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["submission"]["input_kind"] == "repository_url"
    assert payload["execution"]["backend"] == "deterministic"
    assert payload["execution"]["fallback_used"] is True
    assert payload["report"]["benchmark_id"] == "repository-url"


def test_submission_mode_validation_reports_missing_fixture_id(client: TestClient) -> None:
    response = client.post(
        "/audits",
        json={
            "input_kind": "demo_fixture",
            "submitted_by": "fixture-test",
        },
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["error"] == "validation_error"
    assert "fixture_id is required for demo_fixture submissions" in payload["detail"][0]["msg"]


def test_create_audit_with_explicit_service_selection(catalog_client: TestClient) -> None:
    response = catalog_client.post(
        "/audits",
        json={
            "input_kind": "demo_fixture",
            "service_id": "shadow-auditor",
            "fixture_id": "vulnerable-bank",
            "submitted_by": "service-test",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["submission"]["service_id"] == "shadow-auditor"
    assert payload["agent"]["id"] == "shadow-auditor"
    assert payload["agent"]["version"] == "1.2.3"
    assert payload["auditor_service"]["service_id"] == "shadow-auditor"
    assert payload["target_auditor_key"].endswith("::shadow-auditor")


def test_same_target_can_be_submitted_to_multiple_auditors(catalog_client: TestClient) -> None:
    default_response = catalog_client.post(
        "/audits",
        json={
            "input_kind": "demo_fixture",
            "fixture_id": "vulnerable-bank",
            "submitted_by": "default-auditor",
        },
    )
    shadow_response = catalog_client.post(
        "/audits",
        json={
            "input_kind": "demo_fixture",
            "service_id": "shadow-auditor",
            "fixture_id": "vulnerable-bank",
            "submitted_by": "shadow-auditor",
        },
    )

    assert default_response.status_code == 201
    assert shadow_response.status_code == 201
    default_payload = default_response.json()
    shadow_payload = shadow_response.json()
    assert default_payload["contract_address"] == shadow_payload["contract_address"]
    assert default_payload["target_key"] == shadow_payload["target_key"]
    assert default_payload["target_auditor_key"] != shadow_payload["target_auditor_key"]


def test_unknown_service_selection_fails_clearly(catalog_client: TestClient) -> None:
    response = catalog_client.post(
        "/audits",
        json={
            "input_kind": "deployed_address",
            "service_id": "missing-auditor",
            "contract_address": "0x1000000000000000000000000000000000000001",
            "submitted_by": "service-test",
        },
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["error"] == "invalid_payload"
    assert "unknown auditor service" in payload["message"]


def test_service_selection_rejects_unsupported_submission_modes(
    catalog_client: TestClient,
) -> None:
    response = catalog_client.post(
        "/audits",
        json={
            "input_kind": "repository_url",
            "service_id": "shadow-auditor",
            "repository_url": "https://github.com/example/vault",
            "submitted_by": "service-test",
        },
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["error"] == "invalid_payload"
    assert "does not support submission mode repository_url" in payload["message"]
