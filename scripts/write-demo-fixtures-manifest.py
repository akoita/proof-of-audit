from __future__ import annotations

import argparse
from datetime import datetime, UTC
import json
from pathlib import Path


def load_env_file(path: Path) -> list[tuple[str, str]]:
    if not path.exists():
        return []

    pairs: list[tuple[str, str]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        pairs.append((key.strip(), value.strip()))
    return pairs


def write_env_file(path: Path, values: dict[str, str]) -> None:
    path.write_text(
        "\n".join(f"{key}={value}" for key, value in values.items()) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Write the generated local demo fixture manifest."
    )
    parser.add_argument("--catalog-file", required=True)
    parser.add_argument("--manifest-file", required=True)
    parser.add_argument("--api-env-file", required=True)
    parser.add_argument("--network", default="anvil-local")
    parser.add_argument("--chain-id", type=int, default=31337)
    parser.add_argument("--rpc-url", default="http://127.0.0.1:8545")
    parser.add_argument(
        "--deployed-contract",
        action="append",
        default=[],
        help="Contract deployment in the form ContractName=0xAddress",
    )
    args = parser.parse_args()

    catalog = json.loads(Path(args.catalog_file).read_text(encoding="utf-8"))

    deployed_addresses: dict[str, str] = {}
    for raw_value in args.deployed_contract:
        contract_name, separator, address = raw_value.partition("=")
        if not separator or not contract_name or not address:
            raise SystemExit(
                f"Invalid --deployed-contract value {raw_value!r}; expected ContractName=0xAddress"
            )
        deployed_addresses[contract_name] = address

    fixtures: list[dict[str, str]] = []
    for fixture in catalog.get("fixtures", []):
        contract_name = fixture["contract_name"]
        address = deployed_addresses.get(contract_name)
        if address is None:
            raise SystemExit(
                f"Missing deployed address for {contract_name} in deployment arguments"
            )
        fixtures.append(
            {
                "id": fixture["id"],
                "label": fixture["label"],
                "contract_name": contract_name,
                "entry_contract": fixture["entry_contract"],
                "benchmark_id": fixture["benchmark_id"],
                "address": address,
                "challenge_proof_uri": fixture["challenge_proof_uri"],
                "note": fixture["note"],
                "source_path": fixture["source_path"],
            }
        )

    manifest = {
        "network": args.network,
        "chain_id": args.chain_id,
        "rpc_url": args.rpc_url,
        "generated_at": datetime.now(UTC).isoformat(),
        "fixtures": fixtures,
    }
    Path(args.manifest_file).write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )

    api_env_path = Path(args.api_env_file)
    env_values = dict(load_env_file(api_env_path))
    env_values["PROOF_OF_AUDIT_DEMO_FIXTURES_FILE"] = args.manifest_file
    write_env_file(api_env_path, env_values)

    print(f"Wrote {args.manifest_file} with {len(fixtures)} demo fixtures.")
    print(f"Updated {args.api_env_file} with PROOF_OF_AUDIT_DEMO_FIXTURES_FILE.")


if __name__ == "__main__":
    main()
