from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "api"))
sys.path.insert(0, str(ROOT_DIR / "agent"))

from proof_of_audit_api.config import ContractConfig


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a stable published auditor registration document."
    )
    parser.add_argument("--manifest-file", required=True)
    parser.add_argument("--deployment-manifest-file")
    parser.add_argument("--output-file", required=True)
    parser.add_argument("--registration-uri", required=True)
    parser.add_argument("--public-web-url", required=True)
    parser.add_argument("--public-api-base-url")
    parser.add_argument("--agent-id", type=int)
    parser.add_argument("--agent-registry")
    return parser.parse_args()


def load_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    args = parse_args()
    manifest_file = Path(args.manifest_file)
    deployment_manifest = load_json(
        Path(args.deployment_manifest_file)
        if args.deployment_manifest_file
        else None
    )

    env = {
        "PROOF_OF_AUDIT_AGENT_MANIFEST_FILE": str(manifest_file),
        "PROOF_OF_AUDIT_AUDITOR_REGISTRATION_URI": args.registration_uri,
        "PROOF_OF_AUDIT_AUDITOR_PUBLIC_WEB_URL": args.public_web_url,
    }
    if args.public_api_base_url:
        env["PROOF_OF_AUDIT_AUDITOR_PUBLIC_API_URL"] = args.public_api_base_url
    if deployment_manifest.get("network"):
        env["PROOF_OF_AUDIT_NETWORK"] = str(deployment_manifest["network"])
    if deployment_manifest.get("chain_id") is not None:
        env["PROOF_OF_AUDIT_CHAIN_ID"] = str(deployment_manifest["chain_id"])
    if deployment_manifest.get("address"):
        env["PROOF_OF_AUDIT_CONTRACT_ADDRESS"] = str(deployment_manifest["address"])
    if deployment_manifest.get("explorer_base_url"):
        env["PROOF_OF_AUDIT_EXPLORER_BASE_URL"] = str(
            deployment_manifest["explorer_base_url"]
        )

    config = ContractConfig.from_env(env)
    payload = config.auditor_registration_document()

    if args.agent_id is not None and args.agent_registry:
        payload["registrations"] = [
            {
                "agentId": args.agent_id,
                "agentRegistry": args.agent_registry,
            }
        ]

    output_file = Path(args.output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote published registration document: {output_file}")
    print(f"Canonical registration URI: {args.registration_uri}")


if __name__ == "__main__":
    main()
