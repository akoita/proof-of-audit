from __future__ import annotations

import argparse
from datetime import datetime, UTC
import json
from pathlib import Path
from typing import Any


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


def load_deployment_records(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None or not path.exists():
        return {}

    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        raw_items = payload.get("items", payload)
        if isinstance(raw_items, dict):
            return {
                str(contract_name): value
                for contract_name, value in raw_items.items()
                if isinstance(value, dict)
            }
        if isinstance(raw_items, list):
            return {
                str(item["contract_name"]): item
                for item in raw_items
                if isinstance(item, dict) and item.get("contract_name")
            }
    raise SystemExit(
        f"Invalid deployment records file {path}; expected an object keyed by contract name or an items list"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Write a demo fixture manifest for local or reusable network deployments."
    )
    parser.add_argument("--catalog-file", required=True)
    parser.add_argument("--manifest-file", required=True)
    parser.add_argument("--api-env-file", required=True)
    parser.add_argument("--network", default="anvil-local")
    parser.add_argument("--chain-id", type=int, default=31337)
    parser.add_argument("--rpc-url", default="http://127.0.0.1:8545")
    parser.add_argument(
        "--deployment-records-file",
        help="Optional JSON file keyed by contract name with extra deployment metadata to merge into each fixture record",
    )
    parser.add_argument(
        "--skip-api-env-update",
        action="store_true",
        help="Write the manifest without mutating the API env file",
    )
    parser.add_argument(
        "--deployed-contract",
        action="append",
        default=[],
        help="Contract deployment in the form ContractName=0xAddress",
    )
    args = parser.parse_args()

    catalog = json.loads(Path(args.catalog_file).read_text(encoding="utf-8"))
    deployment_records = load_deployment_records(
        Path(args.deployment_records_file)
        if args.deployment_records_file
        else None
    )

    deployed_addresses: dict[str, str] = {}
    for raw_value in args.deployed_contract:
        contract_name, separator, address = raw_value.partition("=")
        if not separator or not contract_name or not address:
            raise SystemExit(
                f"Invalid --deployed-contract value {raw_value!r}; expected ContractName=0xAddress"
            )
        deployed_addresses[contract_name] = address

    fixtures: list[dict[str, Any]] = []
    for fixture in catalog.get("fixtures", []):
        contract_name = fixture["contract_name"]
        deployment_record = deployment_records.get(contract_name, {})
        address = deployed_addresses.get(contract_name) or deployment_record.get("address")
        if address is None:
            raise SystemExit(
                f"Missing deployed address for {contract_name} in deployment arguments"
            )
        record = {
            key: value
            for key, value in deployment_record.items()
            if key not in {"contract_name", "address"}
        }
        record.update(
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
        fixtures.append(record)

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

    print(f"Wrote {args.manifest_file} with {len(fixtures)} demo fixtures.")
    if args.skip_api_env_update:
        print("Skipped API env update by request.")
        return

    api_env_path = Path(args.api_env_file)
    env_values = dict(load_env_file(api_env_path))
    env_values["PROOF_OF_AUDIT_DEMO_FIXTURES_FILE"] = args.manifest_file
    write_env_file(api_env_path, env_values)
    print(f"Updated {args.api_env_file} with PROOF_OF_AUDIT_DEMO_FIXTURES_FILE.")


if __name__ == "__main__":
    main()
