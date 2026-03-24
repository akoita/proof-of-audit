from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess


ROOT_DIR = Path(__file__).resolve().parents[2]
WRITE_FIXTURE_MANIFEST_SCRIPT = ROOT_DIR / "scripts" / "write-demo-fixtures-manifest.py"


def test_write_demo_fixtures_manifest_merges_deployment_records_without_touching_env(
    tmp_path: Path,
) -> None:
    catalog_file = tmp_path / "fixtures.catalog.json"
    manifest_file = tmp_path / "fixtures.base-sepolia.json"
    api_env_file = tmp_path / "api.env"
    deployment_records_file = tmp_path / "deployment-records.json"

    catalog_file.write_text(
        json.dumps(
            {
                "fixtures": [
                    {
                        "id": "vulnerable-bank",
                        "label": "Vulnerable Bank",
                        "contract_name": "VulnerableBank",
                        "entry_contract": "VulnerableBank",
                        "benchmark_id": "reentrancy-bank",
                        "challenge_proof_uri": "ipfs://reentrancy-bank/withdraw-drain",
                        "note": "High-confidence reentrancy finding",
                        "source_path": "demo/contracts/VulnerableBank.sol",
                    }
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )
    api_env_file.write_text("KEEP_EXISTING=1\n", encoding="utf-8")
    deployment_records_file.write_text(
        json.dumps(
            {
                "VulnerableBank": {
                    "address": "0x1234567890abcdef1234567890abcdef12345678",
                    "deployment_tx_hash": "0xabc",
                    "deployment_block_number": 42,
                    "deployer_address": "0x5000000000000000000000000000000000000005",
                    "immutable_source_uri": "ipfs://fixture-cid/VulnerableBank.sol",
                    "verification": {
                        "sourcify": {
                            "status": "verified",
                            "command": "forge verify-contract --verifier sourcify ...",
                            "verified_at": "2026-03-24T21:00:00+00:00",
                        },
                        "basescan": {
                            "status": "skipped",
                            "command": "missing-api-key",
                            "reason": "BaseScan verification requires an API key.",
                        },
                    },
                }
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            os.environ.get("PYTHON_BIN") or "python3",
            str(WRITE_FIXTURE_MANIFEST_SCRIPT),
            "--catalog-file",
            str(catalog_file),
            "--manifest-file",
            str(manifest_file),
            "--api-env-file",
            str(api_env_file),
            "--network",
            "base-sepolia",
            "--chain-id",
            "84532",
            "--rpc-url",
            "https://base-sepolia.example.invalid",
            "--deployment-records-file",
            str(deployment_records_file),
            "--skip-api-env-update",
        ],
        cwd=ROOT_DIR,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(manifest_file.read_text(encoding="utf-8"))

    assert "Skipped API env update by request." in result.stdout
    assert payload["network"] == "base-sepolia"
    assert payload["chain_id"] == 84532
    assert payload["rpc_url"] == "https://base-sepolia.example.invalid"
    assert payload["fixtures"][0]["address"] == "0x1234567890abcdef1234567890abcdef12345678"
    assert payload["fixtures"][0]["deployment_tx_hash"] == "0xabc"
    assert payload["fixtures"][0]["deployment_block_number"] == 42
    assert (
        payload["fixtures"][0]["immutable_source_uri"]
        == "ipfs://fixture-cid/VulnerableBank.sol"
    )
    assert payload["fixtures"][0]["verification"]["sourcify"]["status"] == "verified"
    assert payload["fixtures"][0]["verification"]["basescan"]["status"] == "skipped"
    assert api_env_file.read_text(encoding="utf-8") == "KEEP_EXISTING=1\n"
