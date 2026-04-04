from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from proof_of_audit_agent.agent_forge_backend import AgentForgeRuntimeConfig


@dataclass(frozen=True)
class WorkerRuntimeConfig:
    mode: str = "deterministic"
    agent_forge: AgentForgeRuntimeConfig = AgentForgeRuntimeConfig()
    allow_deployed_address_deterministic_fallback: bool = True

    @classmethod
    def from_values(
        cls,
        *,
        mode: str = "deterministic",
        agent_forge_command: str = "python -m proof_of_audit_agent.agent_forge_cli",
        agent_forge_provider: str | None = None,
        agent_forge_model: str | None = None,
        agent_forge_max_iterations: int | None = None,
        agent_forge_runs_home: Path | None = None,
        agent_forge_service_url: str | None = None,
        agent_forge_service_token: str | None = None,
        agent_forge_service_profile_id: str = "proof-of-audit-solidity-v1",
        agent_forge_service_report_schema: str = "proof-of-audit-report-v1",
        agent_forge_service_poll_interval_seconds: float = 0.25,
        agent_forge_service_poll_timeout_seconds: float = 60.0,
        agent_forge_service_request_timeout_seconds: float = 30.0,
        source_bundle_storage_kind: str = "local",
        source_bundle_gcs_bucket: str | None = None,
        source_bundle_gcs_prefix: str = "source-bundles",
        source_bundle_ipfs_api_url: str | None = None,
        source_bundle_ipfs_auth_header: str | None = None,
        sourcify_base_url: str = "https://sourcify.dev/server",
        explorer_api_url: str | None = "https://api.etherscan.io/v2/api",
        explorer_api_key: str | None = None,
        allow_deployed_address_deterministic_fallback: bool = True,
        detectors: tuple[str, ...] | None = None,
        audit_profile: str | None = None,
    ) -> "WorkerRuntimeConfig":
        normalized_mode = (
            mode if mode in {"deterministic", "hybrid", "agent_forge"} else "deterministic"
        )
        return cls(
            mode=normalized_mode,
            agent_forge=AgentForgeRuntimeConfig(
                mode=normalized_mode,
                command=agent_forge_command,
                provider=agent_forge_provider,
                model=agent_forge_model,
                max_iterations=agent_forge_max_iterations,
                runs_home=agent_forge_runs_home,
                service_base_url=agent_forge_service_url.rstrip("/")
                if agent_forge_service_url
                else None,
                service_api_token=agent_forge_service_token,
                service_profile_id=agent_forge_service_profile_id,
                service_report_schema=agent_forge_service_report_schema,
                service_poll_interval_seconds=agent_forge_service_poll_interval_seconds,
                service_poll_timeout_seconds=agent_forge_service_poll_timeout_seconds,
                service_request_timeout_seconds=agent_forge_service_request_timeout_seconds,
                service_source_storage_kind=source_bundle_storage_kind,
                service_source_gcs_bucket=source_bundle_gcs_bucket,
                service_source_gcs_prefix=source_bundle_gcs_prefix,
                service_source_ipfs_api_url=source_bundle_ipfs_api_url,
                service_source_ipfs_auth_header=source_bundle_ipfs_auth_header,
                sourcify_base_url=sourcify_base_url,
                explorer_api_url=explorer_api_url,
                explorer_api_key=explorer_api_key,
                detectors=detectors,
                audit_profile=audit_profile,
            ),
            allow_deployed_address_deterministic_fallback=(
                allow_deployed_address_deterministic_fallback
            ),
        )
