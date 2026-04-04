#!/usr/bin/env python3
"""Validate demo/agents.json against its JSON schema and check cross-field invariants."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENTS_PATH = REPO_ROOT / "demo" / "agents.json"
SCHEMA_PATH = REPO_ROOT / "demo" / "agents.schema.json"


def _validate_schema(manifest: dict, schema: dict) -> list[str]:
    """Best-effort JSON Schema validation (falls back to structural checks if jsonschema is not installed)."""
    try:
        import jsonschema  # type: ignore[import-untyped]

        validator = jsonschema.Draft202012Validator(schema)
        return [e.message for e in sorted(validator.iter_errors(manifest), key=lambda e: list(e.path))]
    except ImportError:
        # Fallback: basic structural validation
        errors: list[str] = []
        if manifest.get("schema_version") != "agent-personas/v1":
            errors.append(f"schema_version must be 'agent-personas/v1', got '{manifest.get('schema_version')}'")
        if not isinstance(manifest.get("agents"), list) or len(manifest["agents"]) == 0:
            errors.append("agents must be a non-empty array")
        return errors


def _validate_invariants(manifest: dict) -> list[str]:
    """Cross-field business rules that JSON Schema alone cannot enforce."""
    errors: list[str] = []
    agents = manifest.get("agents", [])

    # Unique service_ids
    service_ids = [a["service_id"] for a in agents]
    if len(service_ids) != len(set(service_ids)):
        seen: set[str] = set()
        for sid in service_ids:
            if sid in seen:
                errors.append(f"Duplicate service_id: {sid}")
            seen.add(sid)

    # Unique agent_ids
    agent_ids = [a["identity"]["agent_id"] for a in agents]
    if len(agent_ids) != len(set(agent_ids)):
        errors.append(f"Duplicate agent_id values: {agent_ids}")

    # Unique finding_id_prefix
    prefixes = [a["finding_id_prefix"] for a in agents]
    if len(prefixes) != len(set(prefixes)):
        errors.append(f"Duplicate finding_id_prefix values: {prefixes}")

    # Unique anvil_account_index
    indices = [a["identity"]["anvil_account_index"] for a in agents]
    if len(indices) != len(set(indices)):
        errors.append(f"Duplicate anvil_account_index values: {indices}")

    # LLM agents must have env_keys
    for agent in agents:
        if agent.get("runtime_mode") == "agent_forge":
            provider = agent.get("llm_provider")
            if not provider:
                errors.append(f"{agent['service_id']}: agent_forge mode requires llm_provider")
            elif not agent.get("env_keys"):
                errors.append(f"{agent['service_id']}: LLM agent must declare env_keys for API key")

    # Static agents should not have llm_provider
    for agent in agents:
        if agent.get("runtime_mode") in ("deterministic", "hybrid") and agent.get("llm_provider"):
            errors.append(
                f"{agent['service_id']}: static/hybrid agent should not set llm_provider"
            )

    return errors


def main() -> int:
    if not AGENTS_PATH.exists():
        print(f"❌ {AGENTS_PATH} not found", file=sys.stderr)
        return 1
    if not SCHEMA_PATH.exists():
        print(f"❌ {SCHEMA_PATH} not found", file=sys.stderr)
        return 1

    manifest = json.loads(AGENTS_PATH.read_text(encoding="utf-8"))
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    errors: list[str] = []
    errors.extend(_validate_schema(manifest, schema))
    errors.extend(_validate_invariants(manifest))

    if errors:
        print(f"❌ {len(errors)} validation error(s) in {AGENTS_PATH.name}:", file=sys.stderr)
        for err in errors:
            print(f"  • {err}", file=sys.stderr)
        return 1

    agents = manifest["agents"]
    print(f"✅ {AGENTS_PATH.name} is valid — {len(agents)} agent persona(s):")
    for agent in agents:
        mode = agent["runtime_mode"]
        llm = f" ({agent['llm_provider']})" if agent.get("llm_provider") else ""
        detectors = ", ".join(agent["detectors"])
        print(f"  {agent['identity']['agent_id']}. {agent['name']:<28} [{mode}{llm}] detectors=[{detectors}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
