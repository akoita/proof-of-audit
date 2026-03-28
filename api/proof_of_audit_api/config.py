from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Mapping
from proof_of_audit_agent.fixtures import (
    DEFAULT_DEMO_FIXTURES_FILE,
    default_demo_fixtures_file_for_network,
    resolve_demo_fixtures_file,
)

DEFAULT_API_ENV_FILE = Path(__file__).resolve().parents[1] / ".env.local"
DEFAULT_AUDITOR_MANIFEST_FILE = (
    Path(__file__).resolve().parents[2]
    / "agent"
    / "proof_of_audit_agent"
    / "auditor_manifest.json"
)
DEFAULT_DEPLOYMENTS_DIR = Path(__file__).resolve().parents[2] / "deployments"
DEFAULT_PUBLISHED_AUDITOR_REGISTRATION_FILE = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "registrations"
    / "proof-of-audit-auditor.json"
)
DEFAULT_AUDITOR_PUBLIC_WEB_URL = "https://github.com/akoita/proof-of-audit"
DEFAULT_PUBLISHED_AUDITOR_REGISTRATION_URI = (
    "https://raw.githubusercontent.com/akoita/proof-of-audit/main/"
    "docs/registrations/proof-of-audit-auditor.json"
)
OFFICIAL_ERC8004_IDENTITY_REGISTRIES = {
    ("base-sepolia", 84532): "0x8004a818bfb912233c491871b3d84c89a494bd9e",
}
OFFICIAL_ERC8004_VALIDATION_REGISTRIES = {
    ("base-sepolia", 84532): "0x8004b663056a597dffe9eccc1965a193b7388713",
}
DEFAULT_RUNTIME_API_BASE_URL = "http://127.0.0.1:8080"


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


def load_json_file(path: Path | None) -> dict[str, object]:
    if path is None or not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def address_from_private_key(private_key: str | None) -> str | None:
    if not private_key:
        return None
    try:
        from web3 import Web3
    except ImportError:
        return None
    return Web3().eth.account.from_key(private_key).address


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
                "Smart contract review agent that stakes on-chain behind its "
                "published audit judgment."
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
            resolution_policy="manual-review-with-executable-advisory-verifier",
        )

    @classmethod
    def from_payload(cls, payload: object) -> "AuditorProfile":
        if not isinstance(payload, dict):
            return cls.default()
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

    @classmethod
    def from_manifest_file(cls, path: Path | None) -> "AuditorProfile":
        if path is None or not path.exists():
            return cls.default()
        payload = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_payload(payload)

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
    registration_uri: str
    agent_id: int | None
    agent_registry: str | None
    identity_source: str | None
    capability: str
    discovery_path: str
    submit_path: str
    execution_mode: str
    execution_endpoint: str | None
    publish_path_template: str
    challenge_path_template: str
    network: str
    active: bool
    supported_trust: tuple[str, ...]
    settlement_mode: str
    publication_mode: str
    staking_adapter_kind: str
    staking_adapter_address: str | None
    staking_adapter_method: str | None
    publication_scope: str
    registry_contract_address: str | None
    validation_registry_address: str | None
    validation_source: str | None
    validation_request_path_template: str
    validation_response_path_template: str
    reputation_registry_address: str | None
    reputation_source: str | None
    reputation_path_template: str
    submission_modes: tuple[str, ...]
    resolution_modes: tuple[str, ...]
    deterministic_resolution_supported: bool
    manual_fallback_supported: bool

    @classmethod
    def from_payload(cls, payload: object) -> "AuditorServiceRecord | None":
        if not isinstance(payload, dict):
            return None
        service_id = str(payload.get("service_id") or "").strip()
        name = str(payload.get("name") or "").strip()
        manifest_schema = str(payload.get("manifest_schema") or "").strip()
        manifest_hash = str(payload.get("manifest_hash") or "").strip()
        registration_kind = str(payload.get("registration_kind") or "").strip()
        registration_type = str(payload.get("registration_type") or "").strip()
        registration_endpoint = str(payload.get("registration_endpoint") or "").strip()
        registration_uri = str(payload.get("registration_uri") or "").strip()
        capability = str(payload.get("capability") or "").strip()
        discovery_path = str(payload.get("discovery_path") or "").strip()
        submit_path = str(payload.get("submit_path") or "").strip()
        execution_mode = str(payload.get("execution_mode") or "").strip()
        publish_path_template = str(
            payload.get("publish_path_template") or ""
        ).strip()
        challenge_path_template = str(
            payload.get("challenge_path_template") or ""
        ).strip()
        network = str(payload.get("network") or "").strip()
        validation_request_path_template = str(
            payload.get("validation_request_path_template") or ""
        ).strip()
        validation_response_path_template = str(
            payload.get("validation_response_path_template") or ""
        ).strip()
        reputation_path_template = str(
            payload.get("reputation_path_template") or ""
        ).strip()
        settlement_mode = str(payload.get("settlement_mode") or "").strip()
        publication_mode = str(payload.get("publication_mode") or "").strip()
        staking_adapter_kind = str(payload.get("staking_adapter_kind") or "").strip()
        publication_scope = str(payload.get("publication_scope") or "").strip()
        if not all(
            [
                service_id,
                name,
                manifest_schema,
                manifest_hash,
                registration_kind,
                registration_type,
                registration_endpoint,
                registration_uri,
                capability,
                discovery_path,
                submit_path,
                execution_mode,
                publish_path_template,
                challenge_path_template,
                network,
                settlement_mode,
                publication_mode,
                staking_adapter_kind,
                publication_scope,
                validation_request_path_template,
                validation_response_path_template,
                reputation_path_template,
            ]
        ):
            return None
        agent_id_value = payload.get("agent_id")
        agent_id = int(agent_id_value) if isinstance(agent_id_value, int) else None
        return cls(
            service_id=service_id,
            name=name,
            manifest_schema=manifest_schema,
            manifest_hash=manifest_hash,
            registration_kind=registration_kind,
            registration_type=registration_type,
            registration_endpoint=registration_endpoint,
            registration_uri=registration_uri,
            agent_id=agent_id,
            agent_registry=(
                str(payload["agent_registry"])
                if payload.get("agent_registry") is not None
                else None
            ),
            identity_source=(
                str(payload["identity_source"])
                if payload.get("identity_source") is not None
                else None
            ),
            capability=capability,
            discovery_path=discovery_path,
            submit_path=submit_path,
            execution_mode=execution_mode,
            execution_endpoint=(
                str(payload["execution_endpoint"])
                if payload.get("execution_endpoint") is not None
                else None
            ),
            publish_path_template=publish_path_template,
            challenge_path_template=challenge_path_template,
            network=network,
            active=bool(payload.get("active", True)),
            supported_trust=tuple(
                str(item) for item in payload.get("supported_trust", []) if str(item).strip()
            ),
            settlement_mode=settlement_mode,
            publication_mode=publication_mode,
            staking_adapter_kind=staking_adapter_kind,
            staking_adapter_address=(
                str(payload["staking_adapter_address"])
                if payload.get("staking_adapter_address") is not None
                else None
            ),
            staking_adapter_method=(
                str(payload["staking_adapter_method"])
                if payload.get("staking_adapter_method") is not None
                else None
            ),
            publication_scope=publication_scope,
            registry_contract_address=(
                str(payload["registry_contract_address"])
                if payload.get("registry_contract_address") is not None
                else None
            ),
            validation_registry_address=(
                str(payload["validation_registry_address"])
                if payload.get("validation_registry_address") is not None
                else None
            ),
            validation_source=(
                str(payload["validation_source"])
                if payload.get("validation_source") is not None
                else None
            ),
            validation_request_path_template=validation_request_path_template,
            validation_response_path_template=validation_response_path_template,
            reputation_registry_address=(
                str(payload["reputation_registry_address"])
                if payload.get("reputation_registry_address") is not None
                else None
            ),
            reputation_source=(
                str(payload["reputation_source"])
                if payload.get("reputation_source") is not None
                else None
            ),
            reputation_path_template=reputation_path_template,
            submission_modes=tuple(
                str(item) for item in payload.get("submission_modes", []) if str(item).strip()
            ),
            resolution_modes=tuple(
                str(item) for item in payload.get("resolution_modes", []) if str(item).strip()
            ),
            deterministic_resolution_supported=bool(
                payload.get("deterministic_resolution_supported", False)
            ),
            manual_fallback_supported=bool(
                payload.get("manual_fallback_supported", False)
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "service_id": self.service_id,
            "name": self.name,
            "manifest_schema": self.manifest_schema,
            "manifest_hash": self.manifest_hash,
            "registration_kind": self.registration_kind,
            "registration_type": self.registration_type,
            "registration_endpoint": self.registration_endpoint,
            "registration_uri": self.registration_uri,
            "agent_id": self.agent_id,
            "agent_registry": self.agent_registry,
            "identity_source": self.identity_source,
            "capability": self.capability,
            "discovery_path": self.discovery_path,
            "submit_path": self.submit_path,
            "execution_mode": self.execution_mode,
            "execution_endpoint": self.execution_endpoint,
            "publish_path_template": self.publish_path_template,
            "challenge_path_template": self.challenge_path_template,
            "network": self.network,
            "active": self.active,
            "supported_trust": list(self.supported_trust),
            "settlement_mode": self.settlement_mode,
            "publication_mode": self.publication_mode,
            "staking_adapter_kind": self.staking_adapter_kind,
            "staking_adapter_address": self.staking_adapter_address,
            "staking_adapter_method": self.staking_adapter_method,
            "publication_scope": self.publication_scope,
            "registry_contract_address": self.registry_contract_address,
            "validation_registry_address": self.validation_registry_address,
            "validation_source": self.validation_source,
            "validation_request_path_template": self.validation_request_path_template,
            "validation_response_path_template": self.validation_response_path_template,
            "reputation_registry_address": self.reputation_registry_address,
            "reputation_source": self.reputation_source,
            "reputation_path_template": self.reputation_path_template,
            "submission_modes": list(self.submission_modes),
            "resolution_modes": list(self.resolution_modes),
            "deterministic_resolution_supported": self.deterministic_resolution_supported,
            "manual_fallback_supported": self.manual_fallback_supported,
        }


@dataclass(frozen=True)
class AuditorDirectoryEntry:
    service: AuditorServiceRecord
    registration_document: dict[str, object] | None = None


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
    auditor_owner_private_key: str | None
    validator_private_key: str | None
    validator_address: str | None
    demo_fixtures_file: Path | None
    required_stake_wei: int
    required_challenge_bond_wei: int
    challenge_window_seconds: int
    treasury_address: str | None
    protocol_fee_bps: int
    resolution_fee_bps: int
    auditor: AuditorProfile
    auditor_manifest_file: Path | None
    auditor_published_registration_file: Path
    auditor_registration_uri: str
    auditor_public_web_url: str
    auditor_public_api_base_url: str | None
    runtime_api_base_url: str
    auditor_catalog_file: Path | None
    auditor_agent_id: int | None
    auditor_agent_registry: str | None
    auditor_agent_identity_source: str | None
    validation_registry_address: str | None
    validation_bridge_source: str | None
    reputation_registry_address: str | None
    reputation_bridge_source: str | None
    reputation_operator_private_key: str | None
    reputation_operator_address: str | None
    worker_runtime_mode: str
    agent_forge_command: str
    agent_forge_provider: str | None
    agent_forge_model: str | None
    agent_forge_max_iterations: int | None
    agent_forge_runs_home: Path | None
    agent_forge_service_url: str | None
    agent_forge_service_token: str | None
    agent_forge_service_profile_id: str
    agent_forge_service_report_schema: str
    agent_forge_service_poll_interval_seconds: float
    agent_forge_service_poll_timeout_seconds: float
    agent_forge_service_request_timeout_seconds: float
    source_bundle_storage_kind: str
    source_bundle_gcs_bucket: str | None
    source_bundle_gcs_prefix: str
    source_bundle_ipfs_api_url: str | None
    source_bundle_ipfs_auth_header: str | None
    sourcify_base_url: str
    explorer_api_url: str | None
    explorer_api_key: str | None
    challenge_claim_extractor_command: str | None
    challenge_claim_extractor_provider: str | None
    challenge_claim_extractor_model: str | None
    challenge_claim_extractor_min_confidence: str

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
        network = source.get("PROOF_OF_AUDIT_NETWORK", "base-sepolia")
        chain_id_value = int(source.get("PROOF_OF_AUDIT_CHAIN_ID", "84532"))
        official_identity_registry = OFFICIAL_ERC8004_IDENTITY_REGISTRIES.get(
            (network, chain_id_value)
        )
        official_validation_registry = OFFICIAL_ERC8004_VALIDATION_REGISTRIES.get(
            (network, chain_id_value)
        )
        deployment_manifest_file = (
            Path(source["PROOF_OF_AUDIT_DEPLOYMENT_MANIFEST_FILE"])
            if source.get("PROOF_OF_AUDIT_DEPLOYMENT_MANIFEST_FILE")
            else DEFAULT_DEPLOYMENTS_DIR / f"{network}.json"
        )
        deployment_manifest = load_json_file(deployment_manifest_file)
        auditor_identity = deployment_manifest.get("auditor_identity", {})
        if not isinstance(auditor_identity, dict):
            auditor_identity = {}
        validation_bridge = deployment_manifest.get("validation_bridge", {})
        if not isinstance(validation_bridge, dict):
            validation_bridge = {}
        reputation_bridge = deployment_manifest.get("reputation_bridge", {})
        if not isinstance(reputation_bridge, dict):
            reputation_bridge = {}
        registration_document = deployment_manifest.get("registration_document", {})
        if not isinstance(registration_document, dict):
            registration_document = {}
        constructor_args = deployment_manifest.get("constructor_args", {})
        if not isinstance(constructor_args, dict):
            constructor_args = {}
        auditor_catalog_file = (
            Path(source["PROOF_OF_AUDIT_AUDITOR_CATALOG_FILE"])
            if source.get("PROOF_OF_AUDIT_AUDITOR_CATALOG_FILE")
            else None
        )
        manifest_file = (
            Path(source["PROOF_OF_AUDIT_AGENT_MANIFEST_FILE"])
            if source.get("PROOF_OF_AUDIT_AGENT_MANIFEST_FILE")
            else DEFAULT_AUDITOR_MANIFEST_FILE
        )
        return cls(
            network=network,
            chain_id=chain_id_value,
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
            auditor_owner_private_key=source.get(
                "PROOF_OF_AUDIT_AUDITOR_OWNER_PRIVATE_KEY"
            )
            or source.get("PROOF_OF_AUDIT_ARBITER_PRIVATE_KEY")
            or source.get("PROOF_OF_AUDIT_PRIVATE_KEY")
            or None,
            validator_private_key=source.get("PROOF_OF_AUDIT_VALIDATOR_PRIVATE_KEY")
            or source.get("PROOF_OF_AUDIT_AUDITOR_OWNER_PRIVATE_KEY")
            or source.get("PROOF_OF_AUDIT_ARBITER_PRIVATE_KEY")
            or source.get("PROOF_OF_AUDIT_PRIVATE_KEY")
            or None,
            validator_address=source.get("PROOF_OF_AUDIT_VALIDATOR_ADDRESS")
            or address_from_private_key(source.get("PROOF_OF_AUDIT_VALIDATOR_PRIVATE_KEY"))
            or address_from_private_key(source.get("PROOF_OF_AUDIT_AUDITOR_OWNER_PRIVATE_KEY"))
            or address_from_private_key(source.get("PROOF_OF_AUDIT_ARBITER_PRIVATE_KEY"))
            or address_from_private_key(source.get("PROOF_OF_AUDIT_PRIVATE_KEY"))
            or None,
            demo_fixtures_file=resolve_demo_fixtures_file(
                Path(source["PROOF_OF_AUDIT_DEMO_FIXTURES_FILE"])
                if source.get("PROOF_OF_AUDIT_DEMO_FIXTURES_FILE")
                else default_demo_fixtures_file_for_network(network)
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
            treasury_address=(
                source.get("PROOF_OF_AUDIT_TREASURY_ADDRESS")
                or source.get("PROOF_OF_AUDIT_TREASURY")
                or deployment_manifest.get("treasury_address")
                or constructor_args.get("treasury")
                or None
            ),
            protocol_fee_bps=int(
                source.get(
                    "PROOF_OF_AUDIT_PROTOCOL_FEE_BPS",
                    str(
                        constructor_args.get("protocol_fee_bps")
                        or deployment_manifest.get("protocol_fee_bps")
                        or "0"
                    ),
                )
            ),
            resolution_fee_bps=int(
                source.get(
                    "PROOF_OF_AUDIT_RESOLUTION_FEE_BPS",
                    str(
                        constructor_args.get("resolution_fee_bps")
                        or deployment_manifest.get("resolution_fee_bps")
                        or "0"
                    ),
                )
            ),
            auditor=AuditorProfile.from_manifest_file(manifest_file),
            auditor_manifest_file=manifest_file if manifest_file.exists() else None,
            auditor_published_registration_file=Path(
                source.get(
                    "PROOF_OF_AUDIT_AUDITOR_PUBLISHED_REGISTRATION_FILE",
                    str(DEFAULT_PUBLISHED_AUDITOR_REGISTRATION_FILE),
                )
            ),
            auditor_registration_uri=source.get(
                "PROOF_OF_AUDIT_AUDITOR_REGISTRATION_URI",
                str(
                    registration_document.get("uri")
                    or DEFAULT_PUBLISHED_AUDITOR_REGISTRATION_URI
                ),
            ),
            auditor_public_web_url=source.get(
                "PROOF_OF_AUDIT_AUDITOR_PUBLIC_WEB_URL",
                DEFAULT_AUDITOR_PUBLIC_WEB_URL,
            ),
            auditor_public_api_base_url=(
                source.get("PROOF_OF_AUDIT_AUDITOR_PUBLIC_API_URL") or None
            ),
            runtime_api_base_url=(
                source.get("PROOF_OF_AUDIT_RUNTIME_API_URL")
                or source.get("PROOF_OF_AUDIT_AUDITOR_PUBLIC_API_URL")
                or DEFAULT_RUNTIME_API_BASE_URL
            ).rstrip("/"),
            auditor_catalog_file=auditor_catalog_file,
            auditor_agent_id=(
                int(source["PROOF_OF_AUDIT_AUDITOR_AGENT_ID"])
                if source.get("PROOF_OF_AUDIT_AUDITOR_AGENT_ID")
                else (
                    int(auditor_identity["agent_id"])
                    if auditor_identity.get("agent_id") is not None
                    else None
                )
            ),
            auditor_agent_registry=(
                source.get("PROOF_OF_AUDIT_AUDITOR_AGENT_REGISTRY")
                or (
                    str(auditor_identity["registry_address"])
                    if auditor_identity.get("registry_address")
                    else None
                )
            ),
            auditor_agent_identity_source=(
                source.get("PROOF_OF_AUDIT_AUDITOR_IDENTITY_SOURCE")
                or (
                    str(auditor_identity["source"])
                    if auditor_identity.get("source")
                    else (
                        "erc8004-official"
                        if (
                            (
                                source.get("PROOF_OF_AUDIT_AUDITOR_AGENT_REGISTRY")
                                or (
                                    str(auditor_identity["registry_address"])
                                    if auditor_identity.get("registry_address")
                                    else None
                                )
                            )
                            and official_identity_registry
                            == str(
                                source.get("PROOF_OF_AUDIT_AUDITOR_AGENT_REGISTRY")
                                or (
                                    str(auditor_identity["registry_address"])
                                    if auditor_identity.get("registry_address")
                                    else ""
                                )
                            ).lower()
                        )
                        else None
                    )
                )
            ),
            validation_registry_address=(
                source.get("PROOF_OF_AUDIT_VALIDATION_REGISTRY_ADDRESS")
                or (
                    str(validation_bridge["registry_address"])
                    if validation_bridge.get("registry_address")
                    else official_validation_registry
                )
            ),
            validation_bridge_source=(
                source.get("PROOF_OF_AUDIT_VALIDATION_BRIDGE_SOURCE")
                or (
                    str(validation_bridge["source"])
                    if validation_bridge.get("source")
                    else (
                        "erc8004-official"
                        if (
                            official_validation_registry
                            == str(
                                source.get("PROOF_OF_AUDIT_VALIDATION_REGISTRY_ADDRESS")
                                or (
                                    str(validation_bridge["registry_address"])
                                    if validation_bridge.get("registry_address")
                                    else official_validation_registry or ""
                                )
                            ).lower()
                        )
                        else None
                    )
                )
            ),
            reputation_registry_address=(
                source.get("PROOF_OF_AUDIT_REPUTATION_REGISTRY_ADDRESS")
                or (
                    str(reputation_bridge["registry_address"])
                    if reputation_bridge.get("registry_address")
                    else None
                )
            ),
            reputation_bridge_source=(
                source.get("PROOF_OF_AUDIT_REPUTATION_BRIDGE_SOURCE")
                or (
                    str(reputation_bridge["source"])
                    if reputation_bridge.get("source")
                    else None
                )
            ),
            reputation_operator_private_key=source.get(
                "PROOF_OF_AUDIT_REPUTATION_OPERATOR_PRIVATE_KEY"
            )
            or source.get("PROOF_OF_AUDIT_VALIDATOR_PRIVATE_KEY")
            or source.get("PROOF_OF_AUDIT_AUDITOR_OWNER_PRIVATE_KEY")
            or source.get("PROOF_OF_AUDIT_ARBITER_PRIVATE_KEY")
            or source.get("PROOF_OF_AUDIT_PRIVATE_KEY")
            or None,
            reputation_operator_address=source.get("PROOF_OF_AUDIT_REPUTATION_OPERATOR_ADDRESS")
            or address_from_private_key(
                source.get("PROOF_OF_AUDIT_REPUTATION_OPERATOR_PRIVATE_KEY")
            )
            or address_from_private_key(source.get("PROOF_OF_AUDIT_VALIDATOR_PRIVATE_KEY"))
            or address_from_private_key(source.get("PROOF_OF_AUDIT_AUDITOR_OWNER_PRIVATE_KEY"))
            or address_from_private_key(source.get("PROOF_OF_AUDIT_ARBITER_PRIVATE_KEY"))
            or address_from_private_key(source.get("PROOF_OF_AUDIT_PRIVATE_KEY"))
            or None,
            worker_runtime_mode=source.get(
                "PROOF_OF_AUDIT_WORKER_RUNTIME_MODE",
                "deterministic",
            ),
            agent_forge_command=source.get(
                "PROOF_OF_AUDIT_AGENT_FORGE_COMMAND",
                "python -m proof_of_audit_agent.agent_forge_cli",
            ),
            agent_forge_provider=source.get("PROOF_OF_AUDIT_AGENT_FORGE_PROVIDER")
            or None,
            agent_forge_model=source.get("PROOF_OF_AUDIT_AGENT_FORGE_MODEL") or None,
            agent_forge_max_iterations=(
                int(source["PROOF_OF_AUDIT_AGENT_FORGE_MAX_ITERATIONS"])
                if source.get("PROOF_OF_AUDIT_AGENT_FORGE_MAX_ITERATIONS")
                else None
            ),
            agent_forge_runs_home=(
                Path(source["PROOF_OF_AUDIT_AGENT_FORGE_RUNS_HOME"])
                if source.get("PROOF_OF_AUDIT_AGENT_FORGE_RUNS_HOME")
                else None
            ),
            agent_forge_service_url=(
                source.get("PROOF_OF_AUDIT_AGENT_FORGE_SERVICE_URL") or None
            ),
            agent_forge_service_token=(
                source.get("PROOF_OF_AUDIT_AGENT_FORGE_SERVICE_TOKEN") or None
            ),
            agent_forge_service_profile_id=source.get(
                "PROOF_OF_AUDIT_AGENT_FORGE_SERVICE_PROFILE_ID",
                "proof-of-audit-solidity-v1",
            ),
            agent_forge_service_report_schema=source.get(
                "PROOF_OF_AUDIT_AGENT_FORGE_SERVICE_REPORT_SCHEMA",
                "proof-of-audit-report-v1",
            ),
            agent_forge_service_poll_interval_seconds=float(
                source.get(
                    "PROOF_OF_AUDIT_AGENT_FORGE_SERVICE_POLL_INTERVAL_SECONDS",
                    "0.25",
                )
            ),
            agent_forge_service_poll_timeout_seconds=float(
                source.get(
                    "PROOF_OF_AUDIT_AGENT_FORGE_SERVICE_POLL_TIMEOUT_SECONDS",
                    "60",
                )
            ),
            agent_forge_service_request_timeout_seconds=float(
                source.get(
                    "PROOF_OF_AUDIT_AGENT_FORGE_SERVICE_REQUEST_TIMEOUT_SECONDS",
                    "30",
                )
            ),
            source_bundle_storage_kind=source.get(
                "PROOF_OF_AUDIT_SOURCE_BUNDLE_STORAGE_KIND",
                "local",
            ).strip().lower(),
            source_bundle_gcs_bucket=(
                source.get("PROOF_OF_AUDIT_SOURCE_BUNDLE_GCS_BUCKET") or None
            ),
            source_bundle_gcs_prefix=source.get(
                "PROOF_OF_AUDIT_SOURCE_BUNDLE_GCS_PREFIX",
                "source-bundles",
            ),
            source_bundle_ipfs_api_url=(
                source.get("PROOF_OF_AUDIT_SOURCE_BUNDLE_IPFS_API_URL") or None
            ),
            source_bundle_ipfs_auth_header=(
                source.get("PROOF_OF_AUDIT_SOURCE_BUNDLE_IPFS_AUTH_HEADER") or None
            ),
            sourcify_base_url=source.get(
                "PROOF_OF_AUDIT_SOURCIFY_BASE_URL",
                "https://sourcify.dev/server",
            ).rstrip("/"),
            explorer_api_url=(
                source.get("PROOF_OF_AUDIT_EXPLORER_API_URL")
                or "https://api.etherscan.io/v2/api"
            ),
            explorer_api_key=(
                source.get("PROOF_OF_AUDIT_EXPLORER_API_KEY")
                or source.get("BASESCAN_API_KEY")
                or source.get("PROOF_OF_AUDIT_VERIFY_API_KEY")
                or None
            ),
            challenge_claim_extractor_command=(
                source.get("PROOF_OF_AUDIT_CHALLENGE_CLAIM_EXTRACTOR_COMMAND")
                or None
            ),
            challenge_claim_extractor_provider=(
                source.get("PROOF_OF_AUDIT_CHALLENGE_CLAIM_EXTRACTOR_PROVIDER")
                or None
            ),
            challenge_claim_extractor_model=(
                source.get("PROOF_OF_AUDIT_CHALLENGE_CLAIM_EXTRACTOR_MODEL")
                or None
            ),
            challenge_claim_extractor_min_confidence=(
                source.get(
                    "PROOF_OF_AUDIT_CHALLENGE_CLAIM_EXTRACTOR_MIN_CONFIDENCE",
                    "medium",
                )
                or "medium"
            ),
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

    def auditor_registration_document(self) -> dict[str, object]:
        payload = self.auditor.to_registration_dict()
        extra_services = [
            service.to_dict()
            for service in self.auditor.services
            if service.name not in {"web", "api", "registration"}
        ]
        services: list[dict[str, object]] = [
            {
                "name": "web",
                "endpoint": self.auditor_public_web_url,
            },
            {
                "name": "registration",
                "endpoint": self.auditor_registration_uri,
            },
        ]
        if self.auditor_public_api_base_url:
            services.append(
                {
                    "name": "api",
                    "endpoint": f"{self.auditor_public_api_base_url.rstrip('/')}/auditor",
                    "version": f"v{self.auditor.version}",
                }
            )
        payload["services"] = services + extra_services
        extension = dict(payload.get("x-proof-of-audit", {}))
        extension.update(
            {
                "registrationUri": self.auditor_registration_uri,
                "discoveryPath": "/auditor",
                "submitPath": "/audits",
                "publishPathTemplate": "/audits/{id}/publish",
                "challengePathTemplate": "/audits/{id}/challenge",
                "resolvePathTemplate": "/audits/{id}/resolve",
                "validationRequestPathTemplate": "/audits/{id}/validation/request",
                "validationResponsePathTemplate": "/audits/{id}/validation/response",
                "reputationPathTemplate": "/auditors/{id}/reputation",
                "submissionModes": [
                    "demo_fixture",
                    "deployed_address",
                    "source_bundle",
                ],
                "resolutionModes": [
                    "advisory_verifier",
                    "manual_fallback",
                ],
                "network": self.network,
                "chainId": self.chain_id,
            }
        )
        if self.contract_address:
            extension["settlementContractAddress"] = self.contract_address
        if self.validation_registry_address:
            extension["validationRegistryAddress"] = self.validation_registry_address
        if self.validation_bridge_source:
            extension["validationSource"] = self.validation_bridge_source
        if self.reputation_registry_address:
            extension["reputationRegistryAddress"] = self.reputation_registry_address
        if self.reputation_bridge_source:
            extension["reputationSource"] = self.reputation_bridge_source
        payload["x-proof-of-audit"] = extension
        if (
            not payload.get("registrations")
            and self.auditor_agent_id is not None
            and self.auditor_agent_registry
        ):
            payload["registrations"] = [
                {
                    "agentId": self.auditor_agent_id,
                    "agentRegistry": self.auditor_agent_registry,
                }
            ]
        return payload

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
            registration_uri=self.auditor_registration_uri,
            agent_id=self.auditor_agent_id,
            agent_registry=self.auditor_agent_registry,
            identity_source=self.auditor_agent_identity_source,
            capability=capability,
            discovery_path="/auditor",
            submit_path="/audits",
            execution_mode="local_worker",
            execution_endpoint=None,
            publish_path_template="/audits/{id}/publish",
            challenge_path_template="/audits/{id}/challenge",
            network=self.network,
            active=self.auditor.active,
            supported_trust=self.auditor.supported_trust,
            settlement_mode="native_proof_of_audit",
            publication_mode="api_mediated",
            staking_adapter_kind="native_proof_of_audit",
            staking_adapter_address=self.contract_address,
            staking_adapter_method="publishAudit",
            publication_scope="submit_selected_claim",
            registry_contract_address=self.contract_address,
            validation_registry_address=self.validation_registry_address,
            validation_source=self.validation_bridge_source,
            validation_request_path_template="/audits/{id}/validation/request",
            validation_response_path_template="/audits/{id}/validation/response",
            reputation_registry_address=self.reputation_registry_address,
            reputation_source=self.reputation_bridge_source,
            reputation_path_template="/auditors/{id}/reputation",
            submission_modes=(
                "demo_fixture",
                "deployed_address",
                "source_bundle",
                "repository_url",
            ),
            resolution_modes=("advisory_verifier", "manual_fallback"),
            deterministic_resolution_supported=False,
            manual_fallback_supported=True,
        )

    @property
    def auditor_directory_entries(self) -> tuple[AuditorDirectoryEntry, ...]:
        entries: list[AuditorDirectoryEntry] = [
            AuditorDirectoryEntry(
                service=self.auditor_service,
                registration_document=self.auditor_registration_document(),
            )
        ]
        if self.auditor_catalog_file is None or not self.auditor_catalog_file.exists():
            return tuple(entries)

        payload = load_json_file(self.auditor_catalog_file)
        raw_items = payload.get("items", [])
        if not isinstance(raw_items, list):
            return tuple(entries)

        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                continue
            service = AuditorServiceRecord.from_payload(raw_item.get("service"))
            if service is None or service.service_id == self.auditor_service.service_id:
                continue
            registration_document = raw_item.get("registration_document")
            entries.append(
                AuditorDirectoryEntry(
                    service=service,
                    registration_document=(
                        registration_document
                        if isinstance(registration_document, dict)
                        else None
                    ),
                )
            )
        return tuple(entries)

    @property
    def auditor_services(self) -> tuple[AuditorServiceRecord, ...]:
        return tuple(entry.service for entry in self.auditor_directory_entries)

    def auditor_service_by_id(self, service_id: str) -> AuditorServiceRecord | None:
        normalized_service_id = service_id.strip()
        for entry in self.auditor_directory_entries:
            if entry.service.service_id == normalized_service_id:
                return entry.service
        return None

    def auditor_registration_document_by_service_id(
        self, service_id: str
    ) -> dict[str, object] | None:
        normalized_service_id = service_id.strip()
        for entry in self.auditor_directory_entries:
            if entry.service.service_id == normalized_service_id:
                return entry.registration_document
        return None

    def auditor_profile_by_service_id(self, service_id: str) -> AuditorProfile | None:
        normalized_service_id = service_id.strip()
        if not normalized_service_id:
            return self.auditor

        service = self.auditor_service_by_id(normalized_service_id)
        if service is None:
            return None
        if service.service_id == self.auditor_service.service_id:
            return self.auditor

        registration_document = self.auditor_registration_document_by_service_id(
            normalized_service_id
        )
        if isinstance(registration_document, dict):
            profile = AuditorProfile.from_payload(registration_document)
            defaults = AuditorProfile.default()
            return AuditorProfile(
                registration_type=(
                    profile.registration_type
                    if profile.registration_type != defaults.registration_type
                    else service.registration_type
                ),
                id=(
                    profile.id
                    if profile.id != defaults.id or profile.name != defaults.name
                    else service.service_id
                ),
                name=(
                    profile.name
                    if profile.name != defaults.name or profile.id != defaults.id
                    else service.name
                ),
                version=profile.version,
                manifest_schema=(
                    profile.manifest_schema
                    if profile.manifest_schema != defaults.manifest_schema
                    else service.manifest_schema
                ),
                service_type=profile.service_type,
                description=profile.description,
                image=profile.image,
                services=profile.services,
                x402_support=profile.x402_support,
                active=service.active and profile.active,
                registrations=profile.registrations,
                supported_trust=profile.supported_trust or service.supported_trust,
                capabilities=profile.capabilities or (service.capability,),
                operator=profile.operator,
                resolution_policy=profile.resolution_policy,
            )

        defaults = AuditorProfile.default()
        return AuditorProfile(
            registration_type=service.registration_type,
            id=service.service_id,
            name=service.name,
            version=defaults.version,
            manifest_schema=service.manifest_schema,
            service_type=service.capability,
            description=defaults.description,
            image=defaults.image,
            services=defaults.services,
            x402_support=defaults.x402_support,
            active=service.active,
            registrations=defaults.registrations,
            supported_trust=service.supported_trust or defaults.supported_trust,
            capabilities=(service.capability,),
            operator=defaults.operator,
            resolution_policy=defaults.resolution_policy,
        )
