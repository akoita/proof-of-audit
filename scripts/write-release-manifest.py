from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Write or update a deployment manifest for a contract release."
    )
    parser.add_argument("--manifest-file", required=True)
    parser.add_argument("--contract-name")
    parser.add_argument("--network")
    parser.add_argument("--chain-id", type=int)
    parser.add_argument("--address")
    parser.add_argument("--status")
    parser.add_argument("--arbiter")
    parser.add_argument("--rpc-url")
    parser.add_argument("--explorer-base-url")
    parser.add_argument("--required-stake-wei")
    parser.add_argument("--required-challenge-bond-wei")
    parser.add_argument("--challenge-window-seconds", type=int)
    parser.add_argument("--deployment-tx-hash")
    parser.add_argument("--deployment-block-number", type=int)
    parser.add_argument("--deployer-address")
    parser.add_argument("--constructor-args-json")
    parser.add_argument("--constructor-args-hex")
    parser.add_argument("--verification-status")
    parser.add_argument("--verification-provider")
    parser.add_argument("--verification-command")
    parser.add_argument("--verified-at")
    parser.add_argument("--registration-document-uri")
    parser.add_argument("--registration-document-file")
    parser.add_argument("--registration-source-manifest")
    parser.add_argument("--auditor-identity-registry-address")
    parser.add_argument("--auditor-identity-agent-id", type=int)
    parser.add_argument("--auditor-identity-owner")
    parser.add_argument("--auditor-identity-admin")
    parser.add_argument("--auditor-identity-registration-uri")
    parser.add_argument("--auditor-identity-deploy-tx-hash")
    parser.add_argument("--auditor-identity-register-tx-hash")
    parser.add_argument("--notes")
    return parser.parse_args()


def load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def set_if_present(target: dict[str, Any], key: str, value: Any) -> None:
    if value is not None:
        target[key] = value


def main() -> None:
    args = parse_args()
    manifest_file = Path(args.manifest_file)
    manifest = load_manifest(manifest_file)

    set_if_present(manifest, "contract_name", args.contract_name)
    set_if_present(manifest, "network", args.network)
    set_if_present(manifest, "chain_id", args.chain_id)
    set_if_present(manifest, "address", args.address)
    set_if_present(manifest, "status", args.status)
    set_if_present(manifest, "arbiter", args.arbiter)
    set_if_present(manifest, "rpc_url", args.rpc_url)
    set_if_present(manifest, "explorer_base_url", args.explorer_base_url)
    set_if_present(manifest, "required_stake_wei", args.required_stake_wei)
    set_if_present(
        manifest,
        "required_challenge_bond_wei",
        args.required_challenge_bond_wei,
    )
    set_if_present(
        manifest,
        "challenge_window_seconds",
        args.challenge_window_seconds,
    )
    set_if_present(manifest, "deployment_tx_hash", args.deployment_tx_hash)
    set_if_present(
        manifest,
        "deployment_block_number",
        args.deployment_block_number,
    )
    set_if_present(manifest, "deployer_address", args.deployer_address)
    set_if_present(manifest, "notes", args.notes)

    constructor_args = manifest.get("constructor_args", {})
    if args.constructor_args_json:
        constructor_args.update(json.loads(args.constructor_args_json))
    if args.constructor_args_hex is not None:
        constructor_args["encoded"] = args.constructor_args_hex
    if constructor_args:
        manifest["constructor_args"] = constructor_args

    verification = manifest.get("verification", {})
    set_if_present(verification, "status", args.verification_status)
    set_if_present(verification, "provider", args.verification_provider)
    set_if_present(verification, "command", args.verification_command)
    set_if_present(verification, "verified_at", args.verified_at)
    if verification:
        manifest["verification"] = verification

    registration_document = manifest.get("registration_document", {})
    set_if_present(registration_document, "uri", args.registration_document_uri)
    set_if_present(registration_document, "file", args.registration_document_file)
    set_if_present(
        registration_document,
        "source_manifest",
        args.registration_source_manifest,
    )
    if registration_document:
        manifest["registration_document"] = registration_document

    auditor_identity = manifest.get("auditor_identity", {})
    set_if_present(
        auditor_identity,
        "registry_address",
        args.auditor_identity_registry_address,
    )
    set_if_present(auditor_identity, "agent_id", args.auditor_identity_agent_id)
    set_if_present(auditor_identity, "owner", args.auditor_identity_owner)
    set_if_present(auditor_identity, "admin", args.auditor_identity_admin)
    set_if_present(
        auditor_identity,
        "registration_uri",
        args.auditor_identity_registration_uri,
    )
    set_if_present(
        auditor_identity,
        "deploy_tx_hash",
        args.auditor_identity_deploy_tx_hash,
    )
    set_if_present(
        auditor_identity,
        "register_tx_hash",
        args.auditor_identity_register_tx_hash,
    )
    if auditor_identity:
        manifest["auditor_identity"] = auditor_identity

    manifest["updated_at"] = datetime.now(UTC).isoformat()

    manifest_file.parent.mkdir(parents=True, exist_ok=True)
    manifest_file.write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Wrote deployment manifest: {manifest_file}")
    if manifest.get("address"):
        print(f"Recorded contract address: {manifest['address']}")


if __name__ == "__main__":
    main()
