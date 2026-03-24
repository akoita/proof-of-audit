from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from proof_of_audit_agent.agent_forge_backend import AgentForgeRuntimeConfig


@dataclass(frozen=True)
class WorkerRuntimeConfig:
    mode: str = "deterministic"
    agent_forge: AgentForgeRuntimeConfig = AgentForgeRuntimeConfig()

    @classmethod
    def from_values(
        cls,
        *,
        mode: str = "deterministic",
        agent_forge_command: str = "python -m agent_forge.cli",
        agent_forge_provider: str | None = None,
        agent_forge_model: str | None = None,
        agent_forge_max_iterations: int | None = None,
        agent_forge_runs_home: Path | None = None,
        sourcify_base_url: str = "https://sourcify.dev/server",
        explorer_api_url: str | None = "https://api.etherscan.io/v2/api",
        explorer_api_key: str | None = None,
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
                sourcify_base_url=sourcify_base_url,
                explorer_api_url=explorer_api_url,
                explorer_api_key=explorer_api_key,
            ),
        )
