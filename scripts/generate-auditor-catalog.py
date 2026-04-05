#!/usr/bin/env python3
"""Generate an auditor catalog file from demo/agents.json.

The output catalog feeds the existing ``PROOF_OF_AUDIT_AUDITOR_CATALOG_FILE``
mechanism in :class:`ContractConfig` so the platform can discover and route
to multiple agent services without hardcoded service definitions.

Usage:
    python scripts/generate-auditor-catalog.py \
        --agents-manifest demo/agents.json \
        --output deployments/auditor-catalog.json \
        [--network anvil-local] \
        [--api-base-url http://127.0.0.1:8080]
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any


DEFAULT_NETWORK = "anvil-local"
DEFAULT_API_BASE_URL = "http://127.0.0.1:8080"
DEFAULT_MANIFEST_SCHEMA = "https://eips.ethereum.org/EIPS/eip-8004#registration-v1"


def _build_service_record(agent: dict[str, Any], network: str, api_base_url: str) -> dict[str, Any]:
    """Build an AuditorServiceRecord-compatible payload from an agent persona."""
    service_id = agent["service_id"]
    name = agent["name"]
    identity = agent.get("identity", {})
    agent_id = identity.get("agent_id")
    capabilities = agent.get("capabilities", [])
    profile = agent.get("profile", "")
    detectors = agent.get("detectors", [])
    runtime_mode = agent.get("runtime_mode", "hybrid")

    manifest_hash = sha256(
        json.dumps(agent, sort_keys=True).encode()
    ).hexdigest()[:16]

    return {
        "service_id": service_id,
        "name": name,
        "manifest_schema": DEFAULT_MANIFEST_SCHEMA,
        "manifest_hash": manifest_hash,
        "registration_kind": "eip-8004",
        "registration_type": DEFAULT_MANIFEST_SCHEMA,
        "registration_endpoint": f"{api_base_url}/auditors/{service_id}/registration",
        "registration_uri": (
            f"https://raw.githubusercontent.com/akoita/proof-of-audit/main/"
            f"docs/registrations/{service_id}.json"
        ),
        "agent_id": agent_id,
        "agent_registry": None,
        "identity_source": "agent_manifest",
        "capability": capabilities[0] if capabilities else "audit_contract",
        "discovery_path": f"/auditors/{service_id}",
        "submit_path": "/audits",
        "execution_mode": "local_worker",
        "execution_endpoint": None,
        "publish_path_template": "/audits/{audit_id}/publish",
        "challenge_path_template": "/audits/{audit_id}/challenge",
        "network": network,
        "active": True,
        "supported_trust": ["stake_backed"],
        "settlement_mode": "contract",
        "publication_mode": "api_then_chain",
        "staking_adapter_kind": "contract",
        "staking_adapter_address": None,
        "staking_adapter_method": None,
        "publication_scope": "full",
        "registry_contract_address": None,
        "validation_registry_address": None,
        "validation_source": None,
        "validation_request_path_template": "/audits/{audit_id}/validation/request",
        "validation_response_path_template": "/audits/{audit_id}/validation/response",
        "reputation_registry_address": None,
        "reputation_source": None,
        "reputation_path_template": "/auditors/{service_id}/reputation",
        "submission_modes": [
            "demo_fixture",
            "deployed_address",
            "source_bundle",
            "repository_url",
        ],
        "resolution_modes": ["advisory_verifier", "manual_fallback"],
        "deterministic_resolution_supported": False,
        "manual_fallback_supported": True,
        # Extra fields for per-agent worker scoping
        "profile_id": profile,
        "detectors": detectors,
        "runtime_mode": runtime_mode,
        "capabilities": capabilities,
        "challenge_strategy": agent.get("challenge_strategy"),
        "description": agent.get("description", ""),
        "image": agent.get("image"),
    }


def _build_registration_document(agent: dict[str, Any], api_base_url: str) -> dict[str, Any]:
    """Build a minimal registration document for a persona."""
    service_id = agent["service_id"]
    identity = agent.get("identity", {})
    return {
        "type": DEFAULT_MANIFEST_SCHEMA,
        "id": service_id,
        "name": agent["name"],
        "version": "0.1.0",
        "manifest_schema": DEFAULT_MANIFEST_SCHEMA,
        "service_type": "audit_contract",
        "description": agent.get("description", ""),
        "operator": identity.get("operator", "Proof-of-Audit"),
        "registration_endpoint": f"{api_base_url}/auditors/{service_id}/registration",
        "api_base_url": api_base_url,
        "capabilities": agent.get("capabilities", []),
        "detectors": agent.get("detectors", []),
        "profile": agent.get("profile", ""),
        "challenge_strategy": agent.get("challenge_strategy"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate auditor catalog from demo/agents.json"
    )
    parser.add_argument(
        "--agents-manifest",
        default="demo/agents.json",
    )
    parser.add_argument(
        "--output",
        default="deployments/auditor-catalog.json",
    )
    parser.add_argument("--network", default=DEFAULT_NETWORK)
    parser.add_argument("--api-base-url", default=DEFAULT_API_BASE_URL)
    parser.add_argument(
        "--exclude-primary",
        action="store_true",
        help="Exclude services whose service_id matches the primary auditor (proof-of-audit-auditor).",
    )
    args = parser.parse_args()

    manifest_path = Path(args.agents_manifest)
    if not manifest_path.exists():
        print(f"Agents manifest not found: {manifest_path}")
        return 1

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    agents = manifest.get("agents", [])
    if not agents:
        print("No agents found in manifest.")
        return 1

    items: list[dict[str, Any]] = []
    for agent in agents:
        service_id = agent["service_id"]
        if args.exclude_primary and service_id == "proof-of-audit-auditor":
            continue
        items.append({
            "service": _build_service_record(agent, args.network, args.api_base_url),
            "registration_document": _build_registration_document(agent, args.api_base_url),
        })

    catalog = {
        "schema_version": "auditor-catalog/v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "network": args.network,
        "item_count": len(items),
        "items": items,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
    print(f"✓ Generated auditor catalog with {len(items)} services → {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
