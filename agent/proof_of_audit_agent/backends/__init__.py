from __future__ import annotations

import os
from typing import Mapping

from proof_of_audit_agent.backends.base import (
    EvidenceExecutionBackend,
    EvidenceExecutionResult,
)
from proof_of_audit_agent.backends.local_docker import LocalDockerBackend
from proof_of_audit_agent.backends.local_subprocess import LocalSubprocessBackend

DEFAULT_EXECUTABLE_EVIDENCE_BACKEND = "local_subprocess"


def build_execution_backend(
    *,
    forge_bin: str = "forge",
    executor: object | None = None,
    env: Mapping[str, str] | None = None,
    which: object | None = None,
) -> EvidenceExecutionBackend:
    source = dict(os.environ if env is None else env)
    backend_name = source.get(
        "PROOF_OF_AUDIT_EXECUTABLE_EVIDENCE_BACKEND",
        DEFAULT_EXECUTABLE_EVIDENCE_BACKEND,
    ).strip() or DEFAULT_EXECUTABLE_EVIDENCE_BACKEND
    if backend_name == "local_subprocess":
        return LocalSubprocessBackend(
            executable_name=forge_bin,
            executor=executor,
            which=which,
        )
    if backend_name == "docker":
        return LocalDockerBackend(
            image=source.get("PROOF_OF_AUDIT_EXECUTABLE_EVIDENCE_DOCKER_IMAGE", ""),
            docker_bin=source.get(
                "PROOF_OF_AUDIT_EXECUTABLE_EVIDENCE_DOCKER_BIN", "docker"
            ),
            network=source.get(
                "PROOF_OF_AUDIT_EXECUTABLE_EVIDENCE_DOCKER_NETWORK", "bridge"
            ),
            cpus=source.get("PROOF_OF_AUDIT_EXECUTABLE_EVIDENCE_DOCKER_CPUS", "1.0"),
            pids_limit=int(
                source.get(
                    "PROOF_OF_AUDIT_EXECUTABLE_EVIDENCE_DOCKER_PIDS_LIMIT",
                    "256",
                )
            ),
            executor=executor,
            which=which,
        )
    raise ValueError(f"Unsupported executable evidence backend: {backend_name!r}")

__all__ = [
    "build_execution_backend",
    "DEFAULT_EXECUTABLE_EVIDENCE_BACKEND",
    "EvidenceExecutionBackend",
    "EvidenceExecutionResult",
    "LocalDockerBackend",
    "LocalSubprocessBackend",
]
