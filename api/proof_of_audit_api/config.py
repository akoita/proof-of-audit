from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
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
class AuditorServiceEndpoint:
    name: str
    endpoint: str
    version: str | None = None

    @classmethod
    def from_payload(cls, payload: object) -> "AuditorServiceEndpoint | None":
        if not isinstance(payload, dict):
            return None
        name = str(payload.get("name") or "").strip()
        endpoint = str(payload.get("endpoint") or "").strip()
        if not name or not endpoint:
            return None
        version = payload.get("version")
        return cls(
            name=name,
            endpoint=endpoint,
            version=str(version) if version is not None else None,
        )

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "name": self.name,
            "endpoint": self.endpoint,
        }
        if self.version:
            payload["version"] = self.version
        return payload


@dataclass(frozen=True)
class AuditorRegistrationRef:
    agent_id: int
    agent_registry: str

    @classmethod
    def from_payload(cls, payload: object) -> "AuditorRegistrationRef | None":
        if not isinstance(payload, dict):
            return None
        agent_id = payload.get("agentId")
        agent_registry = str(payload.get("agentRegistry") or "").strip()
        if not isinstance(agent_id, int) or not agent_registry:
            return None
        return cls(agent_id=agent_id, agent_registry=agent_registry)

    def to_dict(self) -> dict[str, object]:
        return {
            "agentId": self.agent_id,
            "agentRegistry": self.agent_registry,
        }


@dataclass(frozen=True)
class AuditorProfile:
    registration_type: str
    id: str
    name: str
    version: str
    manifest_schema: str
    service_type: str
    description: str
    image: str
    services: tuple[AuditorServiceEndpoint, ...]
    x402_support: bool
    active: bool
    registrations: tuple[AuditorRegistrationRef, ...]
    supported_trust: tuple[str, ...]
    capabilities: tuple[str, ...]
    operator: str
    resolution_policy: str

    @classmethod
    def default(cls) -> "AuditorProfile":
        return cls(
            registration_type="https://eips.ethereum.org/EIPS/eip-8004#registration-v1",
            id="proof-of-audit-auditor",
            name="Proof-of-Audit Auditor",
            version="0.1.0",
            manifest_schema="https://eips.ethereum.org/EIPS/eip-8004#registration-v1",
            service_type="audit_contract",
            description=(
                "Deterministic smart contract review agent that stakes on-chain behind "
                "its published audit judgment."
            ),
            image=(
                "data:image/svg+xml;utf8,"
                "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 96 96'>"
                "<rect width='96' height='96' rx='18' fill='%230f1f4b'/>"
                "<path d='M24 24h48v48H24z' fill='none' stroke='%23f28d52' stroke-width='6'/>"
                "<circle cx='48' cy='48' r='14' fill='%23f6f1e8'/>"
                "</svg>"
            ),
            services=(
                AuditorServiceEndpoint(
                    name="web",
                    endpoint="https://github.com/akoita/proof-of-audit",
                ),
                AuditorServiceEndpoint(
                    name="api",
                    endpoint="http://127.0.0.1:8080/auditor/registration",
                    version="v0.2.0",
                ),
            ),
            x402_support=False,
            active=True,
            registrations=(),
            supported_trust=("crypto-economic",),
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
        defaults = cls.default()
        extensions = payload.get("x-proof-of-audit")
        if not isinstance(extensions, dict):
            extensions = {}
        services = tuple(
            endpoint
            for raw_service in payload.get("services", defaults.services)
            if (endpoint := AuditorServiceEndpoint.from_payload(raw_service)) is not None
        )
        if not services:
            services = defaults.services
        registrations = tuple(
            registration
            for raw_registration in payload.get("registrations", defaults.registrations)
            if (
                registration := AuditorRegistrationRef.from_payload(raw_registration)
            )
            is not None
        )
        supported_trust = tuple(
            str(item)
            for item in payload.get("supportedTrust", defaults.supported_trust)
            if str(item).strip()
        )
        return cls(
            registration_type=str(
                payload.get("type")
                or payload.get("manifest_schema")
                or defaults.registration_type
            ),
            id=str(
                payload.get("id")
                or extensions.get("id")
                or defaults.id
            ),
            name=str(payload.get("name", defaults.name)),
            version=str(
                payload.get("version")
                or extensions.get("version")
                or defaults.version
            ),
            manifest_schema=str(
                payload.get("manifest_schema")
                or payload.get("type")
                or defaults.manifest_schema
            ),
            service_type=str(
                payload.get("service_type")
                or extensions.get("serviceType")
                or defaults.service_type
            ),
            description=str(payload.get("description", defaults.description)),
            image=str(payload.get("image", defaults.image)),
            services=services,
            x402_support=bool(payload.get("x402Support", defaults.x402_support)),
            active=bool(payload.get("active", defaults.active)),
            registrations=registrations,
            supported_trust=supported_trust or defaults.supported_trust,
            capabilities=tuple(
                str(item)
                for item in payload.get(
                    "capabilities",
                    extensions.get("capabilities", defaults.capabilities),
                )
            ),
            operator=str(
                payload.get("operator")
                or extensions.get("operator")
                or defaults.operator
            ),
            resolution_policy=str(
                payload.get("resolution_policy")
                or extensions.get("resolutionPolicy")
                or defaults.resolution_policy
            ),
        )

    def to_registration_dict(self) -> dict[str, object]:
        return {
            "type": self.registration_type,
            "name": self.name,
            "description": self.description,
            "image": self.image,
            "services": [service.to_dict() for service in self.services],
            "x402Support": self.x402_support,
            "active": self.active,
            "registrations": [
                registration.to_dict() for registration in self.registrations
            ],
            "supportedTrust": list(self.supported_trust),
            "x-proof-of-audit": {
                "id": self.id,
                "version": self.version,
                "serviceType": self.service_type,
                "capabilities": list(self.capabilities),
                "operator": self.operator,
                "resolutionPolicy": self.resolution_policy,
            },
        }

    def to_dict(self) -> dict[str, object]:
        payload = self.to_registration_dict()
        payload.update(
            {
                "id": self.id,
                "version": self.version,
                "manifest_schema": self.manifest_schema,
                "service_type": self.service_type,
                "capabilities": list(self.capabilities),
                "operator": self.operator,
                "resolution_policy": self.resolution_policy,
            }
        )
        return payload


@dataclass(frozen=True)
class AuditorServiceRecord:
    service_id: str
    name: str
    manifest_schema: str
    manifest_hash: str
    registration_kind: str
    registration_type: str
    registration_endpoint: str
    capability: str
    discovery_path: str
    submit_path: str
    publish_path_template: str
    challenge_path_template: str
    network: str
    active: bool
    supported_trust: tuple[str, ...]
    registry_contract_address: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "service_id": self.service_id,
            "name": self.name,
            "manifest_schema": self.manifest_schema,
            "manifest_hash": self.manifest_hash,
            "registration_kind": self.registration_kind,
            "registration_type": self.registration_type,
            "registration_endpoint": self.registration_endpoint,
            "capability": self.capability,
            "discovery_path": self.discovery_path,
            "submit_path": self.submit_path,
            "publish_path_template": self.publish_path_template,
            "challenge_path_template": self.challenge_path_template,
            "network": self.network,
            "active": self.active,
            "supported_trust": list(self.supported_trust),
            "registry_contract_address": self.registry_contract_address,
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
    auditor_manifest_file: Path | None

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
            auditor_manifest_file=manifest_file if manifest_file.exists() else None,
        )

    @property
    def deployment_ready(self) -> bool:
        return bool(self.contract_address and self.rpc_url)

    def transaction_url(self, tx_hash: str) -> str:
        return f"{self.explorer_base_url}/tx/{tx_hash}"

    @property
    def auditor_manifest_hash(self) -> str:
        if self.auditor_manifest_file and self.auditor_manifest_file.exists():
            content = self.auditor_manifest_file.read_text(encoding="utf-8")
        else:
            content = json.dumps(self.auditor.to_dict(), sort_keys=True)
        return sha256(content.encode("utf-8")).hexdigest()

    @property
    def auditor_service(self) -> AuditorServiceRecord:
        capability = (
            self.auditor.capabilities[0]
            if self.auditor.capabilities
            else self.auditor.service_type
        )
        return AuditorServiceRecord(
            service_id=self.auditor.id,
            name=self.auditor.name,
            manifest_schema=self.auditor.manifest_schema,
            manifest_hash=self.auditor_manifest_hash,
            registration_kind="offchain_manifest",
            registration_type=self.auditor.registration_type,
            registration_endpoint="/auditor/registration",
            capability=capability,
            discovery_path="/auditor",
            submit_path="/audits",
            publish_path_template="/audits/{id}/publish",
            challenge_path_template="/audits/{id}/challenge",
            network=self.network,
            active=self.auditor.active,
            supported_trust=self.auditor.supported_trust,
            registry_contract_address=self.contract_address,
        )
