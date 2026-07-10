from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from proof_of_audit_api.app import create_app
from proof_of_audit_api.config import ContractConfig


def write_manifest(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def test_contract_config_loads_erc8004_shaped_manifest(tmp_path: Path) -> None:
    manifest_file = write_manifest(
        tmp_path / "auditor_manifest.json",
        {
            "type": "https://eips.ethereum.org/EIPS/eip-8004#registration-v1",
            "name": "Proof-of-Audit Auditor",
            "description": "ERC-8004-shaped registration document.",
            "image": "https://example.invalid/auditor.png",
            "services": [
                {"name": "web", "endpoint": "https://example.invalid"},
                {
                    "name": "api",
                    "endpoint": "https://example.invalid/auditor/registration",
                    "version": "v0.3.0",
                },
            ],
            "x402Support": False,
            "active": True,
            "registrations": [],
            "supportedTrust": ["crypto-economic"],
            "x-proof-of-audit": {
                "id": "proof-of-audit-auditor",
                "version": "0.3.0",
                "serviceType": "audit_contract",
                "capabilities": ["audit_contract", "review_challenge_evidence"],
                "operator": "Proof-of-Audit",
                "resolutionPolicy": "manual-review-with-executable-advisory-verifier",
            },
        },
    )

    config = ContractConfig.from_env(
        {
            "PROOF_OF_AUDIT_AGENT_MANIFEST_FILE": str(manifest_file),
            "PROOF_OF_AUDIT_AUDITOR_REGISTRATION_URI": "https://registry.example.invalid/auditors/proof-of-audit-auditor.json",
            "PROOF_OF_AUDIT_AUDITOR_PUBLIC_WEB_URL": "https://proof-of-audit.example.invalid",
            "PROOF_OF_AUDIT_AUDITOR_PUBLIC_API_URL": "https://api.proof-of-audit.example.invalid",
            "PROOF_OF_AUDIT_AUDITOR_AGENT_ID": "7",
            "PROOF_OF_AUDIT_AUDITOR_AGENT_REGISTRY": "0x0000000000000000000000000000000000000A11",
        }
    )

    assert config.auditor.registration_type == "https://eips.ethereum.org/EIPS/eip-8004#registration-v1"
    assert config.auditor.manifest_schema == "https://eips.ethereum.org/EIPS/eip-8004#registration-v1"
    assert config.auditor.services[1].name == "api"
    assert config.auditor.services[1].version == "v0.3.0"
    assert config.auditor.supported_trust == ("crypto-economic",)
    assert config.auditor.id == "proof-of-audit-auditor"
    assert config.auditor.version == "0.3.0"
    assert config.auditor.service_type == "audit_contract"
    assert config.auditor.capabilities == (
        "audit_contract",
        "review_challenge_evidence",
    )
    registration = config.auditor_registration_document()
    assert registration["services"][0]["endpoint"] == "https://proof-of-audit.example.invalid"
    assert registration["services"][1]["endpoint"] == "https://registry.example.invalid/auditors/proof-of-audit-auditor.json"
    assert registration["services"][2]["endpoint"] == "https://api.proof-of-audit.example.invalid/auditor"
    assert registration["x-proof-of-audit"]["registrationUri"] == "https://registry.example.invalid/auditors/proof-of-audit-auditor.json"
    assert registration["registrations"] == [
        {
            "agentId": 7,
            "agentRegistry": "0x0000000000000000000000000000000000000A11",
        }
    ]


def test_contract_config_backfills_erc8004_fields_from_legacy_manifest(tmp_path: Path) -> None:
    manifest_file = write_manifest(
        tmp_path / "legacy_auditor_manifest.json",
        {
            "id": "legacy-auditor",
            "name": "Legacy Auditor",
            "version": "0.1.0",
            "manifest_schema": "proof-of-audit/auditor-service@v1",
            "service_type": "audit_contract",
            "description": "Older manifest format.",
            "capabilities": ["audit_contract"],
            "operator": "Legacy Operator",
            "resolution_policy": "manual-review-with-executable-advisory-verifier",
        },
    )

    config = ContractConfig.from_env(
        {"PROOF_OF_AUDIT_AGENT_MANIFEST_FILE": str(manifest_file)}
    )

    registration = config.auditor_registration_document()
    assert registration["type"] == "proof-of-audit/auditor-service@v1"
    assert registration["services"]
    assert registration["supportedTrust"] == ["crypto-economic"]
    assert registration["x-proof-of-audit"]["id"] == "legacy-auditor"
    assert registration["x-proof-of-audit"]["serviceType"] == "audit_contract"


def test_auditor_registration_endpoint_returns_standards_oriented_document(
    tmp_path: Path,
) -> None:
    manifest_file = write_manifest(
        tmp_path / "auditor_manifest.json",
        {
            "type": "https://eips.ethereum.org/EIPS/eip-8004#registration-v1",
            "name": "Proof-of-Audit Auditor",
            "description": "Standards-oriented document.",
            "image": "https://example.invalid/auditor.png",
            "services": [
                {
                    "name": "api",
                    "endpoint": "https://example.invalid/auditor/registration",
                    "version": "v0.3.0",
                }
            ],
            "x402Support": False,
            "active": True,
            "registrations": [],
            "supportedTrust": ["crypto-economic"],
            "x-proof-of-audit": {
                "id": "proof-of-audit-auditor",
                "version": "0.3.0",
                "serviceType": "audit_contract",
                "capabilities": ["audit_contract"],
                "operator": "Proof-of-Audit",
                "resolutionPolicy": "manual-review-with-executable-advisory-verifier",
            },
        },
    )
    env_file = tmp_path / ".env.local"
    env_file.write_text(
        "\n".join(
            [
                "PROOF_OF_AUDIT_NETWORK=anvil-local",
                "PROOF_OF_AUDIT_CHAIN_ID=31337",
                f"PROOF_OF_AUDIT_AGENT_MANIFEST_FILE={manifest_file}",
                "PROOF_OF_AUDIT_AUDITOR_REGISTRATION_URI=https://registry.example.invalid/auditors/proof-of-audit-auditor.json",
                "PROOF_OF_AUDIT_AUDITOR_PUBLIC_WEB_URL=https://proof-of-audit.example.invalid",
                "PROOF_OF_AUDIT_AUDITOR_PUBLIC_API_URL=https://api.proof-of-audit.example.invalid",
                "PROOF_OF_AUDIT_AUDITOR_AGENT_ID=7",
                "PROOF_OF_AUDIT_AUDITOR_AGENT_REGISTRY=0x0000000000000000000000000000000000000A11",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    data_root = tmp_path / "data"
    data_root.mkdir()

    client = TestClient(create_app(data_root=data_root, env_file=env_file))

    registration = client.get("/auditor/registration")
    assert registration.status_code == 200
    payload = registration.json()
    assert payload["type"] == "https://eips.ethereum.org/EIPS/eip-8004#registration-v1"
    assert payload["services"][0]["endpoint"] == "https://proof-of-audit.example.invalid"
    assert payload["services"][1]["endpoint"] == "https://registry.example.invalid/auditors/proof-of-audit-auditor.json"
    assert payload["services"][2]["endpoint"] == "https://api.proof-of-audit.example.invalid/auditor"
    assert payload["supportedTrust"] == ["crypto-economic"]
    assert payload["x-proof-of-audit"]["id"] == "proof-of-audit-auditor"
    assert payload["x-proof-of-audit"]["registrationUri"] == "https://registry.example.invalid/auditors/proof-of-audit-auditor.json"
    assert payload["registrations"] == [
        {
            "agentId": 7,
            "agentRegistry": "0x0000000000000000000000000000000000000A11",
        }
    ]

    discovery = client.get("/auditor")
    assert discovery.status_code == 200
    discovery_payload = discovery.json()
    assert discovery_payload["registration_type"] == "https://eips.ethereum.org/EIPS/eip-8004#registration-v1"
    assert discovery_payload["registration_endpoint"] == "/auditor/registration"
    assert discovery_payload["registration_uri"] == "https://registry.example.invalid/auditors/proof-of-audit-auditor.json"
    assert discovery_payload["agent_id"] == 7
    assert discovery_payload["agent_registry"] == "0x0000000000000000000000000000000000000A11"
    assert discovery_payload["supported_trust"] == ["crypto-economic"]
