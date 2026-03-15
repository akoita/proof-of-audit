from __future__ import annotations

import argparse
from pathlib import Path


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key] = value
    return values


def write_env(path: Path, values: dict[str, str]) -> None:
    lines = [f"{key}={value}" for key, value in values.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Merge local identity and validation settings into api/.env.local."
    )
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--auditor-agent-id", required=True)
    parser.add_argument("--auditor-agent-registry", required=True)
    parser.add_argument("--identity-source", default="project-local-custom")
    parser.add_argument("--auditor-owner-private-key", required=True)
    parser.add_argument("--validation-registry-address", required=True)
    parser.add_argument("--validation-bridge-source", default="project-local-custom")
    parser.add_argument("--validator-private-key", required=True)
    parser.add_argument("--validator-address", required=True)
    args = parser.parse_args()

    env_file = Path(args.env_file)
    values = load_env(env_file)
    values.update(
        {
            "PROOF_OF_AUDIT_AUDITOR_AGENT_ID": args.auditor_agent_id,
            "PROOF_OF_AUDIT_AUDITOR_AGENT_REGISTRY": args.auditor_agent_registry,
            "PROOF_OF_AUDIT_AUDITOR_IDENTITY_SOURCE": args.identity_source,
            "PROOF_OF_AUDIT_AUDITOR_OWNER_PRIVATE_KEY": args.auditor_owner_private_key,
            "PROOF_OF_AUDIT_VALIDATION_REGISTRY_ADDRESS": args.validation_registry_address,
            "PROOF_OF_AUDIT_VALIDATION_BRIDGE_SOURCE": args.validation_bridge_source,
            "PROOF_OF_AUDIT_VALIDATOR_PRIVATE_KEY": args.validator_private_key,
            "PROOF_OF_AUDIT_VALIDATOR_ADDRESS": args.validator_address,
        }
    )
    write_env(env_file, values)
    print(f"Updated {env_file} with local identity and validation settings")


if __name__ == "__main__":
    main()
