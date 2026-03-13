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
DEPLOY_LOCAL_SCRIPT = ROOT_DIR / "scripts" / "deploy-local.sh"
DEFAULT_LOCAL_DEPLOYER = Web3.to_checksum_address(
    "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"
)


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


def run_deploy_local(
    *,
    rpc_url: str,
    chain_id: int,
    network: str,
    manifest_file: Path,
    api_env_file: Path,
    web_env_file: Path,
    python_bin: str,
    force_redeploy: bool = False,
) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "ANVIL_RPC_URL": rpc_url,
        "ANVIL_CHAIN_ID": str(chain_id),
        "PROOF_OF_AUDIT_NETWORK": network,
        "LOCAL_DEPLOYMENT_MANIFEST_FILE": str(manifest_file),
        "LOCAL_DEPLOYMENT_API_ENV_FILE": str(api_env_file),
        "LOCAL_DEPLOYMENT_WEB_ENV_FILE": str(web_env_file),
        "PYTHON_BIN": python_bin,
    }
    if force_redeploy:
        env["LOCAL_DEPLOYMENT_FORCE_REDEPLOY"] = "1"
    return subprocess.run(
        [str(DEPLOY_LOCAL_SCRIPT)],
        cwd=ROOT_DIR,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


def load_manifest(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.system_e2e
def test_deploy_local_reuses_existing_contract_when_manifest_matches(tmp_path) -> None:
    anvil = start_anvil(port=9661, chain_id=31351)
    try:
        manifest_file = tmp_path / "localhost.json"
        api_env_file = tmp_path / "api.env.local"
        web_env_file = tmp_path / "web.env.local"
        rpc_url = "http://127.0.0.1:9661"
        network = "anvil-idempotent"
        python_bin = os.environ.get("PYTHON_BIN") or "python3"

        first = run_deploy_local(
            rpc_url=rpc_url,
            chain_id=31351,
            network=network,
            manifest_file=manifest_file,
            api_env_file=api_env_file,
            web_env_file=web_env_file,
            python_bin=python_bin,
        )
        first_manifest = load_manifest(manifest_file)
        web3 = Web3(HTTPProvider(rpc_url))
        deployer_nonce_after_first = web3.eth.get_transaction_count(DEFAULT_LOCAL_DEPLOYER)

        second = run_deploy_local(
            rpc_url=rpc_url,
            chain_id=31351,
            network=network,
            manifest_file=manifest_file,
            api_env_file=api_env_file,
            web_env_file=web_env_file,
            python_bin=python_bin,
        )
        second_manifest = load_manifest(manifest_file)
        deployer_nonce_after_second = web3.eth.get_transaction_count(DEFAULT_LOCAL_DEPLOYER)

        assert "Deployment mode: fresh deployment." in first.stdout
        assert "Reusing existing ProofOfAudit deployment" in second.stdout
        assert "Deployment mode: reused existing deployment." in second.stdout
        assert first_manifest["address"] == second_manifest["address"]
        assert deployer_nonce_after_first == deployer_nonce_after_second
        assert api_env_file.read_text(encoding="utf-8").count(
            "PROOF_OF_AUDIT_CONTRACT_ADDRESS"
        ) == 1
        assert web_env_file.read_text(encoding="utf-8").count(
            "NEXT_PUBLIC_PROOF_OF_AUDIT_CONTRACT_ADDRESS"
        ) == 1
    finally:
        anvil.terminate()
        anvil.wait(timeout=20)


@pytest.mark.system_e2e
def test_deploy_local_can_force_a_fresh_redeployment(tmp_path) -> None:
    anvil = start_anvil(port=9662, chain_id=31352)
    try:
        manifest_file = tmp_path / "localhost.json"
        api_env_file = tmp_path / "api.env.local"
        web_env_file = tmp_path / "web.env.local"
        rpc_url = "http://127.0.0.1:9662"
        network = "anvil-force-redeploy"
        python_bin = os.environ.get("PYTHON_BIN") or "python3"

        run_deploy_local(
            rpc_url=rpc_url,
            chain_id=31352,
            network=network,
            manifest_file=manifest_file,
            api_env_file=api_env_file,
            web_env_file=web_env_file,
            python_bin=python_bin,
        )
        first_manifest = load_manifest(manifest_file)
        web3 = Web3(HTTPProvider(rpc_url))
        deployer_nonce_after_first = web3.eth.get_transaction_count(DEFAULT_LOCAL_DEPLOYER)

        forced = run_deploy_local(
            rpc_url=rpc_url,
            chain_id=31352,
            network=network,
            manifest_file=manifest_file,
            api_env_file=api_env_file,
            web_env_file=web_env_file,
            python_bin=python_bin,
            force_redeploy=True,
        )
        second_manifest = load_manifest(manifest_file)
        deployer_nonce_after_second = web3.eth.get_transaction_count(DEFAULT_LOCAL_DEPLOYER)

        assert "Force redeploy requested." in forced.stdout
        assert "Deployment mode: fresh deployment." in forced.stdout
        assert first_manifest["address"] != second_manifest["address"]
        assert deployer_nonce_after_second > deployer_nonce_after_first
    finally:
        anvil.terminate()
        anvil.wait(timeout=20)
