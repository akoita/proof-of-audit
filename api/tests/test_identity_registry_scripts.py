from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import time

import pytest
from web3 import HTTPProvider, Web3


ROOT_DIR = Path(__file__).resolve().parents[2]
START_ANVIL_SCRIPT = ROOT_DIR / "scripts" / "start-anvil.sh"
DEPLOY_RELEASE_SCRIPT = ROOT_DIR / "scripts" / "deploy-release.sh"
DEPLOY_IDENTITY_SCRIPT = ROOT_DIR / "scripts" / "deploy-agent-identity.sh"
DEFAULT_LOCAL_DEPLOYER_PRIVATE_KEY = (
    "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
)
DEFAULT_LOCAL_ARBITER = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"
DEFAULT_LOCAL_AUDITOR_OWNER = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"


def wait_for_rpc(rpc_url: str, timeout_seconds: int = 30) -> None:
    web3 = Web3(HTTPProvider(rpc_url))
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            web3.eth.chain_id
        except Exception:
            time.sleep(0.5)
            continue
        return
    raise TimeoutError(f"timed out waiting for RPC at {rpc_url}")


def start_anvil(port: int, chain_id: int) -> subprocess.Popen[str]:
    process = subprocess.Popen(
        [str(START_ANVIL_SCRIPT)],
        cwd=ROOT_DIR,
        env={
            **os.environ,
            "ANVIL_HOST": "127.0.0.1",
            "ANVIL_PORT": str(port),
            "ANVIL_CHAIN_ID": str(chain_id),
        },
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    wait_for_rpc(f"http://127.0.0.1:{port}")
    return process


def load_manifest(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.system_e2e
def test_deploy_agent_identity_registers_auditor_and_refreshes_manifest(
    tmp_path: Path,
) -> None:
    anvil = start_anvil(port=9665, chain_id=31355)
    try:
        manifest_file = tmp_path / "anvil-release.json"
        registration_file = tmp_path / "published-registration.json"
        rpc_url = "http://127.0.0.1:9665"

        subprocess.run(
            [str(DEPLOY_RELEASE_SCRIPT)],
            cwd=ROOT_DIR,
            env={
                **os.environ,
                "PROOF_OF_AUDIT_DEPLOY_NETWORK": "anvil-identity",
                "PROOF_OF_AUDIT_DEPLOY_CHAIN_ID": "31355",
                "PROOF_OF_AUDIT_DEPLOY_RPC_URL": rpc_url,
                "PROOF_OF_AUDIT_EXPLORER_BASE_URL": rpc_url,
                "PROOF_OF_AUDIT_DEPLOYMENT_MANIFEST_FILE": str(manifest_file),
                "PROOF_OF_AUDIT_AUDITOR_PUBLISHED_REGISTRATION_FILE": str(registration_file),
                "PROOF_OF_AUDIT_AUDITOR_REGISTRATION_URI": "https://registry.example.invalid/auditors/proof-of-audit-auditor.json",
                "PROOF_OF_AUDIT_AUDITOR_PUBLIC_WEB_URL": "https://proof-of-audit.example.invalid",
                "PROOF_OF_AUDIT_AUDITOR_PUBLIC_API_URL": "https://api.proof-of-audit.example.invalid",
                "DEPLOYER_PRIVATE_KEY": DEFAULT_LOCAL_DEPLOYER_PRIVATE_KEY,
                "PROOF_OF_AUDIT_ARBITER": DEFAULT_LOCAL_ARBITER,
                "PYTHON_BIN": os.environ.get("PYTHON_BIN") or "python3",
            },
            check=True,
            capture_output=True,
            text=True,
        )

        result = subprocess.run(
            [str(DEPLOY_IDENTITY_SCRIPT)],
            cwd=ROOT_DIR,
            env={
                **os.environ,
                "PROOF_OF_AUDIT_IDENTITY_NETWORK": "anvil-identity",
                "PROOF_OF_AUDIT_IDENTITY_CHAIN_ID": "31355",
                "PROOF_OF_AUDIT_IDENTITY_RPC_URL": rpc_url,
                "PROOF_OF_AUDIT_DEPLOYMENT_MANIFEST_FILE": str(manifest_file),
                "PROOF_OF_AUDIT_AUDITOR_PUBLISHED_REGISTRATION_FILE": str(registration_file),
                "PROOF_OF_AUDIT_AUDITOR_REGISTRATION_URI": "https://registry.example.invalid/auditors/proof-of-audit-auditor.json",
                "PROOF_OF_AUDIT_AUDITOR_PUBLIC_WEB_URL": "https://proof-of-audit.example.invalid",
                "PROOF_OF_AUDIT_AUDITOR_PUBLIC_API_URL": "https://api.proof-of-audit.example.invalid",
                "PROOF_OF_AUDIT_AGENT_REGISTRY_ADMIN": DEFAULT_LOCAL_ARBITER,
                "PROOF_OF_AUDIT_AUDITOR_OWNER": DEFAULT_LOCAL_AUDITOR_OWNER,
                "DEPLOYER_PRIVATE_KEY": DEFAULT_LOCAL_DEPLOYER_PRIVATE_KEY,
                "PROOF_OF_AUDIT_ARBITER": DEFAULT_LOCAL_ARBITER,
                "PYTHON_BIN": os.environ.get("PYTHON_BIN") or "python3",
            },
            check=True,
            capture_output=True,
            text=True,
        )

        manifest = load_manifest(manifest_file)
        registration = load_manifest(registration_file)
        web3 = Web3(HTTPProvider(rpc_url))

        assert "Auditor identity registration complete." in result.stdout
        assert manifest["auditor_identity"]["agent_id"] == 1
        assert (
            manifest["auditor_identity"]["registration_uri"]
            == "https://registry.example.invalid/auditors/proof-of-audit-auditor.json"
        )
        assert (
            manifest["auditor_identity"]["owner"] == DEFAULT_LOCAL_AUDITOR_OWNER
        )
        assert (
            manifest["auditor_identity"]["admin"] == DEFAULT_LOCAL_ARBITER
        )
        assert str(manifest["auditor_identity"]["registry_address"]).startswith("0x")
        assert web3.eth.get_code(
            web3.to_checksum_address(
                str(manifest["auditor_identity"]["registry_address"])
            )
        ) not in (b"", b"\x00")
        assert registration["registrations"] == [
            {
                "agentId": 1,
                "agentRegistry": str(manifest["auditor_identity"]["registry_address"]),
            }
        ]
        assert (
            registration["x-proof-of-audit"]["settlementContractAddress"]
            == manifest["address"]
        )
    finally:
        anvil.terminate()
        anvil.wait(timeout=20)
