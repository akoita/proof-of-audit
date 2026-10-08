from __future__ import annotations

import argparse
import ipaddress
import json
from pathlib import Path
import socket
import sys
from typing import Any
from urllib.parse import urlsplit

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
    args = parser.parse_args()

    has_agent_registry = bool(args.agent_registry and args.agent_registry.strip())
    if (args.agent_id is not None) != has_agent_registry:
        parser.error("--agent-id and --agent-registry must be supplied together")

    public_urls = {
        "--registration-uri": args.registration_uri,
        "--public-web-url": args.public_web_url,
    }
    if args.public_api_base_url and args.public_api_base_url.strip():
        public_urls["--public-api-base-url"] = args.public_api_base_url
    for option, value in public_urls.items():
        if is_loopback_url(value):
            parser.error(f"{option} must not point to a loopback address")

    return args


def is_loopback_url(value: str) -> bool:
    """Return whether a URL points to localhost or an IP loopback address."""
    candidate = value.strip()
    try:
        parsed = urlsplit(candidate)
        if parsed.hostname is None and "://" not in candidate:
            parsed = urlsplit(f"//{candidate}")
        hostname = parsed.hostname
    except ValueError:
        return False

    if not hostname:
        return False
    normalized = hostname.rstrip(".").casefold()
    if normalized == "localhost" or normalized.endswith(".localhost"):
        return True

    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        try:
            address = ipaddress.IPv4Address(socket.inet_aton(normalized))
        except OSError:
            return False
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        return address.ipv4_mapped.is_loopback
    return address.is_loopback


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
    if args.deployment_manifest_file:
        env["PROOF_OF_AUDIT_DEPLOYMENT_MANIFEST_FILE"] = args.deployment_manifest_file
    if args.public_api_base_url and args.public_api_base_url.strip():
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

    if not (args.public_api_base_url and args.public_api_base_url.strip()):
        payload["services"] = [
            service
            for service in payload.get("services", [])
            if not (
                isinstance(service, dict)
                and service.get("name") == "api"
                and is_loopback_url(str(service.get("endpoint") or ""))
            )
        ]

    payload["registrations"] = (
        [
            {
                "agentId": args.agent_id,
                "agentRegistry": args.agent_registry,
            }
        ]
        if args.agent_id is not None and args.agent_registry is not None
        else []
    )

    output_file = Path(args.output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote published registration document: {output_file}")
    print(f"Canonical registration URI: {args.registration_uri}")


if __name__ == "__main__":
    main()
