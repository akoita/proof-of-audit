from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from proof_of_audit_agent.models import AuditReport


@dataclass(frozen=True)
class AuditSubmission:
    audit_id: str | None
    input_kind: str
    network: str | None = None
    chain_id: int | None = None
    contract_address: str | None = None
    fixture_id: str | None = None
    entry_contract: str | None = None
    source_bundle_uri: str | None = None
    source_bundle_label: str | None = None
    repository_url: str | None = None


@dataclass(frozen=True)
class AuditExecution:
    backend: str
    mode: str
    status: str
    source: str
    live_attempted: bool
    fallback_used: bool
    task_prompt: str | None = None
    workspace_dir: str | None = None
    source_path: str | None = None
    report_path: str | None = None
    run_id: str | None = None
    run_dir: str | None = None
    status_url: str | None = None
    logs_url: str | None = None
    source_digest: str | None = None
    profile_id: str | None = None
    provider: str | None = None
    model: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "backend": self.backend,
            "mode": self.mode,
            "status": self.status,
            "source": self.source,
            "live_attempted": self.live_attempted,
            "fallback_used": self.fallback_used,
        }
        optional_values = {
            "task_prompt": self.task_prompt,
            "workspace_dir": self.workspace_dir,
            "source_path": self.source_path,
            "report_path": self.report_path,
            "run_id": self.run_id,
            "run_dir": self.run_dir,
            "status_url": self.status_url,
            "logs_url": self.logs_url,
            "source_digest": self.source_digest,
            "profile_id": self.profile_id,
            "provider": self.provider,
            "model": self.model,
            "error": self.error,
        }
        for key, value in optional_values.items():
            if value is not None:
                payload[key] = value
        return payload


@dataclass(frozen=True)
class AuditExecutionResult:
    report: AuditReport
    execution: AuditExecution | None = None


class AuditorBackend(Protocol):
    @property
    def backend_name(self) -> str: ...

    def run_submission(
        self,
        submission: AuditSubmission,
    ) -> AuditExecutionResult | None: ...
