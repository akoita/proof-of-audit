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
    parser.add_argument("--treasury-address", required=True)
    parser.add_argument("--required-stake-wei", default="10000000000000000")
    parser.add_argument("--required-challenge-bond-wei", default="5000000000000000")
    parser.add_argument("--challenge-window-seconds", default="86400")
    parser.add_argument("--protocol-fee-bps", default="0")
    parser.add_argument("--resolution-fee-bps", default="0")
    parser.add_argument("--deployment-manifest-file")
    parser.add_argument("--api-env-file")
    parser.add_argument("--web-env-file")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    deployment_manifest_file = (
        Path(args.deployment_manifest_file)
        if args.deployment_manifest_file
        else root / "deployments" / "localhost.json"
    )
    api_env_file = (
        Path(args.api_env_file) if args.api_env_file else root / "api" / ".env.local"
    )
    web_env_file = (
        Path(args.web_env_file) if args.web_env_file else root / "web" / ".env.local"
    )

    deployment_manifest = {
        "network": args.network,
        "chain_id": args.chain_id,
        "contract_name": "ProofOfAudit",
        "address": args.contract_address,
        "status": "deployed_locally",
        "arbiter": args.arbiter,
        "treasury_address": args.treasury_address,
        "rpc_url": args.rpc_url,
        "required_stake_wei": args.required_stake_wei,
        "required_challenge_bond_wei": args.required_challenge_bond_wei,
        "challenge_window_seconds": int(args.challenge_window_seconds),
        "protocol_fee_bps": int(args.protocol_fee_bps),
        "resolution_fee_bps": int(args.resolution_fee_bps),
    }
    deployment_manifest_file.parent.mkdir(parents=True, exist_ok=True)
    deployment_manifest_file.write_text(
        json.dumps(deployment_manifest, indent=2) + "\n",
        encoding="utf-8",
    )

    write_env_file(
        api_env_file,
        {
            "PROOF_OF_AUDIT_NETWORK": args.network,
            "PROOF_OF_AUDIT_CHAIN_ID": str(args.chain_id),
            "PROOF_OF_AUDIT_CONTRACT_ADDRESS": args.contract_address,
            "PROOF_OF_AUDIT_EXPLORER_BASE_URL": args.explorer_base_url,
            "PROOF_OF_AUDIT_ARBITER": args.arbiter,
            "PROOF_OF_AUDIT_TREASURY_ADDRESS": args.treasury_address,
            "PROOF_OF_AUDIT_RPC_URL": args.rpc_url,
            "PROOF_OF_AUDIT_PRIVATE_KEY": args.publisher_private_key,
            "PROOF_OF_AUDIT_ARBITER_PRIVATE_KEY": args.arbiter_private_key
            or args.publisher_private_key,
            "PROOF_OF_AUDIT_REQUIRED_STAKE_WEI": args.required_stake_wei,
            "PROOF_OF_AUDIT_REQUIRED_CHALLENGE_BOND_WEI": args.required_challenge_bond_wei,
            "PROOF_OF_AUDIT_CHALLENGE_WINDOW_SECONDS": args.challenge_window_seconds,
            "PROOF_OF_AUDIT_PROTOCOL_FEE_BPS": args.protocol_fee_bps,
            "PROOF_OF_AUDIT_RESOLUTION_FEE_BPS": args.resolution_fee_bps,
        },
    )

    write_env_file(
        web_env_file,
        {
            "PROOF_OF_AUDIT_API_URL": args.api_url,
            "NEXT_PUBLIC_PROOF_OF_AUDIT_API_URL": args.api_url,
            "NEXT_PUBLIC_PROOF_OF_AUDIT_NETWORK": args.network,
            "NEXT_PUBLIC_PROOF_OF_AUDIT_CHAIN_ID": str(args.chain_id),
            "NEXT_PUBLIC_PROOF_OF_AUDIT_CONTRACT_ADDRESS": args.contract_address,
            "NEXT_PUBLIC_PROOF_OF_AUDIT_EXPLORER_BASE_URL": args.explorer_base_url,
        },
    )

    print(f"Wrote {deployment_manifest_file} for {args.contract_address}")
    print(f"Updated {api_env_file}")
    print(f"Updated {web_env_file}")


if __name__ == "__main__":
    main()
