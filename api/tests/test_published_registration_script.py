from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT_DIR = Path(__file__).resolve().parents[2]
REGISTRATION_SCRIPT = ROOT_DIR / "scripts" / "write-published-registration.py"
AUDITOR_MANIFEST = ROOT_DIR / "agent" / "proof_of_audit_agent" / "auditor_manifest.json"
REGISTRATION_URI = "https://registry.example.invalid/auditors/proof-of-audit.json"
PUBLIC_WEB_URL = "https://proof-of-audit.example.invalid"
PUBLIC_API_URL = "https://api.proof-of-audit.example.invalid"
CONTRACT_ADDRESS = "0x1234567890abcdef1234567890abcdef12345678"
AGENT_REGISTRY = "0x8004a818bfb912233c491871b3d84c89a494bd9e"


def write_deployment_manifest(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "network": "base-sepolia",
                "chain_id": 84532,
                "address": CONTRACT_ADDRESS,
                "explorer_base_url": "https://sepolia.basescan.org",
                "auditor_identity": {
                    "agent_id": 1862,
                    "registry_address": AGENT_REGISTRY,
                    "source": "erc8004-official",
                },
            }
        ),
        encoding="utf-8",
    )


def run_generator(
    tmp_path: Path,
    *extra_args: str,
) -> tuple[subprocess.CompletedProcess[str], Path]:
    deployment_manifest = tmp_path / "deployment.json"
    write_deployment_manifest(deployment_manifest)
    output_file = tmp_path / "published-registration.json"
    command = [
        sys.executable,
        str(REGISTRATION_SCRIPT),
        "--manifest-file",
        str(AUDITOR_MANIFEST),
        "--deployment-manifest-file",
        str(deployment_manifest),
        "--output-file",
        str(output_file),
        "--registration-uri",
        REGISTRATION_URI,
        "--public-web-url",
        PUBLIC_WEB_URL,
        *extra_args,
    ]
    result = subprocess.run(
        command,
        cwd=ROOT_DIR,
        env=os.environ.copy(),
        check=False,
        capture_output=True,
        text=True,
    )
    return result, output_file


def test_default_local_api_is_omitted_and_manifest_identity_is_not_inferred(
    tmp_path: Path,
) -> None:
    result, output_file = run_generator(tmp_path)

    assert result.returncode == 0, result.stderr
    registration = json.loads(output_file.read_text(encoding="utf-8"))
    assert registration["registrations"] == []
    assert [service["name"] for service in registration["services"]] == [
        "web",
        "registration",
    ]
    assert "localhost" not in json.dumps(registration).lower()
    assert "127.0.0.1" not in json.dumps(registration)
    assert registration["x-proof-of-audit"]["network"] == "base-sepolia"
    assert registration["x-proof-of-audit"]["chainId"] == 84532
    assert (
        registration["x-proof-of-audit"]["settlementContractAddress"]
        == CONTRACT_ADDRESS
    )


def test_explicit_public_api_and_identity_pair_are_preserved(tmp_path: Path) -> None:
    result, output_file = run_generator(
        tmp_path,
        "--public-api-base-url",
        PUBLIC_API_URL,
        "--agent-id",
        "1862",
        "--agent-registry",
        AGENT_REGISTRY,
    )

    assert result.returncode == 0, result.stderr
    registration = json.loads(output_file.read_text(encoding="utf-8"))
    assert {
        service["name"]: service["endpoint"] for service in registration["services"]
    } == {
        "web": PUBLIC_WEB_URL,
        "registration": REGISTRATION_URI,
        "api": f"{PUBLIC_API_URL}/auditor",
    }
    assert registration["registrations"] == [
        {"agentId": 1862, "agentRegistry": AGENT_REGISTRY}
    ]
    assert (
        registration["x-proof-of-audit"]["settlementContractAddress"]
        == CONTRACT_ADDRESS
    )


@pytest.mark.parametrize(
    ("option", "url"),
    [
        ("--public-api-base-url", "http://localhost:8080"),
        ("--public-api-base-url", "http://127.1:8080"),
        ("--public-web-url", "http://127.0.0.1:3000"),
        ("--registration-uri", "http://[::1]:8000/registration.json"),
    ],
)
def test_loopback_public_urls_are_rejected_before_writing(
    tmp_path: Path,
    option: str,
    url: str,
) -> None:
    result, output_file = run_generator(tmp_path, option, url)

    assert result.returncode != 0
    assert "must not point to a loopback address" in result.stderr
    assert not output_file.exists()


@pytest.mark.parametrize(
    "identity_arg",
    [
        ("--agent-id", "1862"),
        ("--agent-registry", AGENT_REGISTRY),
    ],
)
def test_identity_arguments_must_be_supplied_as_a_pair(
    tmp_path: Path,
    identity_arg: tuple[str, str],
) -> None:
    result, output_file = run_generator(tmp_path, *identity_arg)

    assert result.returncode != 0
    assert "--agent-id and --agent-registry must be supplied together" in result.stderr
    assert not output_file.exists()
