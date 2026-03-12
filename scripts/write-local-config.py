from __future__ import annotations

import argparse
import json
from pathlib import Path


def write_env_file(path: Path, values: dict[str, str]) -> None:
    lines = [f"{key}={value}" for key, value in values.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Write generated local config files after localhost deployment."
    )
    parser.add_argument("--contract-address", required=True)
    parser.add_argument("--arbiter", required=True)
    parser.add_argument("--rpc-url", default="http://127.0.0.1:8545")
    parser.add_argument("--chain-id", type=int, default=31337)
    parser.add_argument("--network", default="anvil-local")
    parser.add_argument("--explorer-base-url", default="http://127.0.0.1:8545")
    parser.add_argument("--api-url", default="http://127.0.0.1:8080")
    parser.add_argument("--publisher-private-key", required=True)
    parser.add_argument("--arbiter-private-key")
    parser.add_argument("--required-stake-wei", default="10000000000000000")
    parser.add_argument("--required-challenge-bond-wei", default="5000000000000000")
    parser.add_argument("--challenge-window-seconds", default="86400")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]

    deployment_manifest = {
        "network": args.network,
        "chain_id": args.chain_id,
        "contract_name": "ProofOfAudit",
        "address": args.contract_address,
        "status": "deployed_locally",
        "arbiter": args.arbiter,
        "rpc_url": args.rpc_url,
        "required_stake_wei": args.required_stake_wei,
        "required_challenge_bond_wei": args.required_challenge_bond_wei,
        "challenge_window_seconds": int(args.challenge_window_seconds),
    }
    (root / "deployments" / "localhost.json").write_text(
        json.dumps(deployment_manifest, indent=2) + "\n",
        encoding="utf-8",
    )

    write_env_file(
        root / "api" / ".env.local",
        {
            "PROOF_OF_AUDIT_NETWORK": args.network,
            "PROOF_OF_AUDIT_CHAIN_ID": str(args.chain_id),
            "PROOF_OF_AUDIT_CONTRACT_ADDRESS": args.contract_address,
            "PROOF_OF_AUDIT_EXPLORER_BASE_URL": args.explorer_base_url,
            "PROOF_OF_AUDIT_ARBITER": args.arbiter,
            "PROOF_OF_AUDIT_RPC_URL": args.rpc_url,
            "PROOF_OF_AUDIT_PRIVATE_KEY": args.publisher_private_key,
            "PROOF_OF_AUDIT_ARBITER_PRIVATE_KEY": args.arbiter_private_key
            or args.publisher_private_key,
            "PROOF_OF_AUDIT_REQUIRED_STAKE_WEI": args.required_stake_wei,
            "PROOF_OF_AUDIT_REQUIRED_CHALLENGE_BOND_WEI": args.required_challenge_bond_wei,
            "PROOF_OF_AUDIT_CHALLENGE_WINDOW_SECONDS": args.challenge_window_seconds,
        },
    )

    write_env_file(
        root / "web" / ".env.local",
        {
            "NEXT_PUBLIC_PROOF_OF_AUDIT_API_URL": args.api_url,
            "NEXT_PUBLIC_PROOF_OF_AUDIT_NETWORK": args.network,
            "NEXT_PUBLIC_PROOF_OF_AUDIT_CHAIN_ID": str(args.chain_id),
            "NEXT_PUBLIC_PROOF_OF_AUDIT_CONTRACT_ADDRESS": args.contract_address,
            "NEXT_PUBLIC_PROOF_OF_AUDIT_EXPLORER_BASE_URL": args.explorer_base_url,
        },
    )

    print(f"Wrote deployments/localhost.json for {args.contract_address}")
    print("Updated api/.env.local")
    print("Updated web/.env.local")


if __name__ == "__main__":
    main()
