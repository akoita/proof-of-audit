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
