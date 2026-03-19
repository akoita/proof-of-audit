from __future__ import annotations

import os
from typing import Mapping

from proof_of_audit_agent.backends.base import (
    EvidenceExecutionBackend,
    EvidenceExecutionResult,
)
from proof_of_audit_agent.backends.gcp_cloud_run import GCPCloudRunBackend
from proof_of_audit_agent.backends.local_docker import LocalDockerBackend
from proof_of_audit_agent.backends.local_subprocess import LocalSubprocessBackend

DEFAULT_EXECUTABLE_EVIDENCE_BACKEND = "local_subprocess"


def build_execution_backend(
    *,
    forge_bin: str = "forge",
    executor: object | None = None,
    env: Mapping[str, str] | None = None,
    which: object | None = None,
    urlopen: object | None = None,
    metadata_urlopen: object | None = None,
    storage_client_factory: object | None = None,
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
    if backend_name == "gcp_cloud_run":
        return GCPCloudRunBackend(
            service_url=source.get(
                "PROOF_OF_AUDIT_EXECUTABLE_EVIDENCE_GCP_CLOUD_RUN_URL", ""
            ),
            audience=source.get(
                "PROOF_OF_AUDIT_EXECUTABLE_EVIDENCE_GCP_CLOUD_RUN_AUDIENCE"
            )
            or None,
            bearer_token=source.get(
                "PROOF_OF_AUDIT_EXECUTABLE_EVIDENCE_GCP_CLOUD_RUN_BEARER_TOKEN"
            )
            or None,
            allow_unauthenticated=source.get(
                "PROOF_OF_AUDIT_EXECUTABLE_EVIDENCE_GCP_CLOUD_RUN_ALLOW_UNAUTHENTICATED",
                "",
            ).strip()
            in {"1", "true", "TRUE", "yes", "YES"},
            staging_bucket=source.get(
                "PROOF_OF_AUDIT_EXECUTABLE_EVIDENCE_GCP_CLOUD_RUN_GCS_BUCKET"
            )
            or None,
            staging_prefix=source.get(
                "PROOF_OF_AUDIT_EXECUTABLE_EVIDENCE_GCP_CLOUD_RUN_GCS_PREFIX",
                "proof-of-audit/evidence",
            ),
            metadata_identity_url=source.get(
                "PROOF_OF_AUDIT_EXECUTABLE_EVIDENCE_GCP_CLOUD_RUN_METADATA_URL",
                source.get(
                    "PROOF_OF_AUDIT_EXECUTABLE_EVIDENCE_GCP_METADATA_IDENTITY_URL",
                    "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity",
                ),
            ),
            urlopen=urlopen,
            metadata_urlopen=metadata_urlopen,
            storage_client_factory=storage_client_factory,
        )
    raise ValueError(f"Unsupported executable evidence backend: {backend_name!r}")

__all__ = [
    "build_execution_backend",
    "DEFAULT_EXECUTABLE_EVIDENCE_BACKEND",
    "EvidenceExecutionBackend",
    "EvidenceExecutionResult",
    "GCPCloudRunBackend",
    "LocalDockerBackend",
    "LocalSubprocessBackend",
]
