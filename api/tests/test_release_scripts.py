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
VERIFY_RELEASE_SCRIPT = ROOT_DIR / "scripts" / "verify-release.sh"
DEFAULT_LOCAL_DEPLOYER_PRIVATE_KEY = (
    "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
)
DEFAULT_LOCAL_ARBITER = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"


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
def test_deploy_release_writes_repeatable_manifest(tmp_path: Path) -> None:
    anvil = start_anvil(port=9663, chain_id=31353)
    try:
        manifest_file = tmp_path / "anvil-release.json"
        registration_file = tmp_path / "published-registration.json"
        rpc_url = "http://127.0.0.1:9663"
        result = subprocess.run(
            [str(DEPLOY_RELEASE_SCRIPT)],
            cwd=ROOT_DIR,
            env={
                **os.environ,
                "PROOF_OF_AUDIT_DEPLOY_NETWORK": "anvil-release",
                "PROOF_OF_AUDIT_DEPLOY_CHAIN_ID": "31353",
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

        manifest = load_manifest(manifest_file)
        registration = load_manifest(registration_file)

        assert "Release deployment complete." in result.stdout
        assert manifest["network"] == "anvil-release"
        assert manifest["chain_id"] == 31353
        assert manifest["status"] == "deployed"
        assert str(manifest["address"]).startswith("0x")
        assert str(manifest["deployment_tx_hash"]).startswith("0x")
        assert manifest["deployment_block_number"] == 1
        assert manifest["verification"]["status"] == "not_requested"
        assert manifest["constructor_args"]["arbiter"] == DEFAULT_LOCAL_ARBITER
        assert str(manifest["constructor_args"]["encoded"]).startswith("0x")
        assert (
            manifest["registration_document"]["uri"]
            == "https://registry.example.invalid/auditors/proof-of-audit-auditor.json"
        )
        assert manifest["registration_document"]["file"] == str(registration_file)
        assert registration["services"][0]["endpoint"] == "https://proof-of-audit.example.invalid"
        assert registration["services"][1]["endpoint"] == "https://registry.example.invalid/auditors/proof-of-audit-auditor.json"
        assert registration["services"][2]["endpoint"] == "https://api.proof-of-audit.example.invalid/auditor"
        assert registration["x-proof-of-audit"]["settlementContractAddress"] == manifest["address"]
    finally:
        anvil.terminate()
        anvil.wait(timeout=20)


@pytest.mark.system_e2e
def test_verify_release_dry_run_uses_recorded_constructor_args(tmp_path: Path) -> None:
    anvil = start_anvil(port=9664, chain_id=31354)
    try:
        manifest_file = tmp_path / "anvil-release.json"
        registration_file = tmp_path / "published-registration.json"
        rpc_url = "http://127.0.0.1:9664"
        subprocess.run(
            [str(DEPLOY_RELEASE_SCRIPT)],
            cwd=ROOT_DIR,
            env={
                **os.environ,
                "PROOF_OF_AUDIT_DEPLOY_NETWORK": "anvil-release-verify",
                "PROOF_OF_AUDIT_DEPLOY_CHAIN_ID": "31354",
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

        manifest = load_manifest(manifest_file)

        result = subprocess.run(
            [str(VERIFY_RELEASE_SCRIPT)],
            cwd=ROOT_DIR,
            env={
                **os.environ,
                "PROOF_OF_AUDIT_DEPLOY_NETWORK": "anvil-release-verify",
                "PROOF_OF_AUDIT_DEPLOY_CHAIN_ID": "31354",
                "PROOF_OF_AUDIT_DEPLOYMENT_MANIFEST_FILE": str(manifest_file),
                "PROOF_OF_AUDIT_VERIFY_API_KEY": "test-api-key",
                "PROOF_OF_AUDIT_VERIFY_DRY_RUN": "1",
                "PYTHON_BIN": os.environ.get("PYTHON_BIN") or "python3",
            },
            check=True,
            capture_output=True,
            text=True,
        )

        assert "forge verify-contract" in result.stdout
        assert str(manifest["address"]) in result.stdout
        assert str(manifest["constructor_args"]["encoded"]) in result.stdout
        assert "Verification dry run enabled" in result.stdout
        assert load_manifest(manifest_file)["verification"]["status"] == "not_requested"
    finally:
        anvil.terminate()
        anvil.wait(timeout=20)
