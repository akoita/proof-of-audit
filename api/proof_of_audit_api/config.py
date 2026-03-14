from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Mapping

from proof_of_audit_agent.fixtures import DEFAULT_DEMO_FIXTURES_FILE, resolve_demo_fixtures_file

DEFAULT_API_ENV_FILE = Path(__file__).resolve().parents[1] / ".env.local"
DEFAULT_AUDITOR_MANIFEST_FILE = (
    Path(__file__).resolve().parents[2]
    / "agent"
    / "proof_of_audit_agent"
    / "auditor_manifest.json"
)


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


@dataclass(frozen=True)
class AuditorProfile:
    id: str
    name: str
    version: str
    service_type: str
    description: str
    capabilities: tuple[str, ...]
    operator: str
    resolution_policy: str

    @classmethod
    def default(cls) -> "AuditorProfile":
        return cls(
            id="proof-of-audit-auditor",
            name="Proof-of-Audit Auditor",
            version="0.1.0",
            service_type="audit_contract",
            description=(
                "Deterministic smart contract review agent that stakes on-chain behind "
                "its published audit judgment."
            ),
            capabilities=(
                "audit_contract",
                "publish_staked_attestation",
                "review_challenge_evidence",
            ),
            operator="Proof-of-Audit",
            resolution_policy="deterministic-first-with-human-fallback",
        )

    @classmethod
    def from_manifest_file(cls, path: Path | None) -> "AuditorProfile":
        if path is None or not path.exists():
            return cls.default()
        payload = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            id=str(payload.get("id", cls.default().id)),
            name=str(payload.get("name", cls.default().name)),
            version=str(payload.get("version", cls.default().version)),
            service_type=str(payload.get("service_type", cls.default().service_type)),
            description=str(payload.get("description", cls.default().description)),
            capabilities=tuple(str(item) for item in payload.get("capabilities", cls.default().capabilities)),
            operator=str(payload.get("operator", cls.default().operator)),
            resolution_policy=str(
                payload.get("resolution_policy", cls.default().resolution_policy)
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "service_type": self.service_type,
            "description": self.description,
            "capabilities": list(self.capabilities),
            "operator": self.operator,
            "resolution_policy": self.resolution_policy,
        }


@dataclass(frozen=True)
class ContractConfig:
    network: str
    chain_id: int
    contract_address: str | None
    explorer_base_url: str
    arbiter: str | None
    rpc_url: str | None
    publisher_private_key: str | None
    arbiter_private_key: str | None
    demo_fixtures_file: Path | None
    required_stake_wei: int
    required_challenge_bond_wei: int
    challenge_window_seconds: int
    auditor: AuditorProfile

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        env_file: Path | None = None,
    ) -> "ContractConfig":
        if env is None:
            source: dict[str, str] = load_env_file(env_file or DEFAULT_API_ENV_FILE)
            source.update(os.environ)
        else:
            source = dict(env)
        manifest_file = (
            Path(source["PROOF_OF_AUDIT_AGENT_MANIFEST_FILE"])
            if source.get("PROOF_OF_AUDIT_AGENT_MANIFEST_FILE")
            else DEFAULT_AUDITOR_MANIFEST_FILE
        )
        return cls(
            network=source.get("PROOF_OF_AUDIT_NETWORK", "base-sepolia"),
            chain_id=int(source.get("PROOF_OF_AUDIT_CHAIN_ID", "84532")),
            contract_address=source.get("PROOF_OF_AUDIT_CONTRACT_ADDRESS") or None,
            explorer_base_url=source.get(
                "PROOF_OF_AUDIT_EXPLORER_BASE_URL",
                "https://sepolia.basescan.org",
            ).rstrip("/"),
            arbiter=source.get("PROOF_OF_AUDIT_ARBITER") or None,
            rpc_url=source.get("PROOF_OF_AUDIT_RPC_URL")
            or source.get("BASE_SEPOLIA_RPC_URL")
            or None,
            publisher_private_key=source.get("PROOF_OF_AUDIT_PRIVATE_KEY") or None,
            arbiter_private_key=source.get("PROOF_OF_AUDIT_ARBITER_PRIVATE_KEY")
            or source.get("PROOF_OF_AUDIT_PRIVATE_KEY")
            or None,
            demo_fixtures_file=resolve_demo_fixtures_file(
                Path(source["PROOF_OF_AUDIT_DEMO_FIXTURES_FILE"])
                if source.get("PROOF_OF_AUDIT_DEMO_FIXTURES_FILE")
                else DEFAULT_DEMO_FIXTURES_FILE
            ),
            required_stake_wei=int(
                source.get("PROOF_OF_AUDIT_REQUIRED_STAKE_WEI", "10000000000000000")
            ),
            required_challenge_bond_wei=int(
                source.get(
                    "PROOF_OF_AUDIT_REQUIRED_CHALLENGE_BOND_WEI",
                    "5000000000000000",
                )
            ),
            challenge_window_seconds=int(
                source.get("PROOF_OF_AUDIT_CHALLENGE_WINDOW_SECONDS", "86400")
            ),
            auditor=AuditorProfile.from_manifest_file(manifest_file),
        )

    @property
    def deployment_ready(self) -> bool:
        return bool(self.contract_address and self.rpc_url)

    def transaction_url(self, tx_hash: str) -> str:
        return f"{self.explorer_base_url}/tx/{tx_hash}"
