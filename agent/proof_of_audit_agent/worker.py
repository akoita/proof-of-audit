from __future__ import annotations

from pathlib import Path

from proof_of_audit_agent.agent_forge_backend import (
    AgentForgeExecutionError,
    AgentForgeBackend,
)
from proof_of_audit_agent.auditor_backend import (
    AuditExecutionResult,
    AuditSubmission,
)
from proof_of_audit_agent.fixtures import DemoFixture
from proof_of_audit_agent.deterministic_auditor_backend import (
    DeterministicAuditorBackend,
)
from proof_of_audit_agent.models import AuditReport
from proof_of_audit_agent.runtime import WorkerRuntimeConfig


class AuditWorker:
    """Returns deterministic reports for demo addresses and safe fallbacks otherwise."""

    def __init__(
        self,
        fixtures_file: Path | None = None,
        *,
        runtime: WorkerRuntimeConfig | None = None,
        workspace_root: Path | None = None,
    ) -> None:
        self.runtime = runtime or WorkerRuntimeConfig()
        self.workspace_root = workspace_root or Path.cwd() / ".proof-of-audit-runtime"
        self.deterministic_backend = DeterministicAuditorBackend(fixtures_file)
        self.agent_forge = AgentForgeBackend(self.runtime.agent_forge, self.workspace_root)

    def run_audit(self, contract_address: str) -> AuditReport:
        return self.deterministic_backend.run_audit(contract_address)

    def list_demo_fixtures(self) -> list[dict[str, str]]:
        return self.deterministic_backend.list_demo_fixtures()

    def require_fixture(self, fixture_id: str | None) -> DemoFixture:
        return self.deterministic_backend.require_fixture(fixture_id)

    def synthetic_contract_address(
        self, source_identifier: str, entry_contract: str | None = None
    ) -> str:
        return self.deterministic_backend.synthetic_contract_address(
            source_identifier,
            entry_contract=entry_contract,
        )

    def run_submission(
        self,
        *,
        audit_id: str | None = None,
        input_kind: str,
        network: str | None = None,
        chain_id: int | None = None,
        contract_address: str | None = None,
        fixture_id: str | None = None,
        entry_contract: str | None = None,
        source_bundle_uri: str | None = None,
        source_bundle_label: str | None = None,
        repository_url: str | None = None,
        runtime_overrides: dict[str, object] | None = None,
    ) -> AuditExecutionResult:
        submission = AuditSubmission(
            audit_id=audit_id,
            input_kind=input_kind,
            network=network,
            chain_id=chain_id,
            contract_address=contract_address,
            fixture_id=fixture_id,
            entry_contract=entry_contract,
            source_bundle_uri=source_bundle_uri,
            source_bundle_label=source_bundle_label,
            repository_url=repository_url,
        )

        # Apply per-agent runtime overrides (detectors, profile) if provided.
        original_runtime = self.agent_forge.runtime
        if runtime_overrides:
            self.agent_forge = AgentForgeBackend(
                self._apply_runtime_overrides(original_runtime, runtime_overrides),
                self.workspace_root,
            )
        try:
            return self._execute_submission(submission)
        finally:
            if runtime_overrides:
                self.agent_forge = AgentForgeBackend(original_runtime, self.workspace_root)

    def _apply_runtime_overrides(
        self,
        base_config: "AgentForgeRuntimeConfig",
        overrides: dict[str, object],
    ) -> "AgentForgeRuntimeConfig":
        """Create a new AgentForgeRuntimeConfig with per-agent overrides applied."""
        from dataclasses import fields as dc_fields
        update: dict[str, object] = {}
        for field in dc_fields(base_config):
            update[field.name] = getattr(base_config, field.name)
        if "detectors" in overrides and overrides["detectors"] is not None:
            raw = overrides["detectors"]
            update["detectors"] = tuple(str(d) for d in raw) if isinstance(raw, (list, tuple)) else base_config.detectors
        if "audit_profile" in overrides and overrides["audit_profile"] is not None:
            update["audit_profile"] = str(overrides["audit_profile"])
        from proof_of_audit_agent.agent_forge_backend import AgentForgeRuntimeConfig as _Cfg
        return _Cfg(**update)

    def _execute_submission(self, submission: AuditSubmission) -> AuditExecutionResult:

        if submission.input_kind == "demo_fixture":
            result = self.deterministic_backend.run_submission(submission)
            assert result is not None
            return result

        if submission.input_kind == "deployed_address":
            live_attempted = submission.audit_id is not None and self.runtime.mode in {
                "hybrid",
                "agent_forge",
            }
            if live_attempted:
                live_result = self.agent_forge.run_submission(submission)
                if live_result is not None:
                    return live_result
            if not self.runtime.allow_deployed_address_deterministic_fallback:
                detail = self.agent_forge.last_error_message
                raise AgentForgeExecutionError(
                    "deployed_address submissions use live hosted agent-forge analysis; local deterministic fallback is disabled for this target type"
                    + (f". Live execution detail: {detail}" if detail else "")
                )
            deterministic_result = self.deterministic_backend.run_submission(submission)
            assert deterministic_result is not None
            if deterministic_result.report.benchmark_id != "unknown":
                return AuditExecutionResult(
                    report=deterministic_result.report,
                    execution=self.agent_forge.fallback_execution(
                        reason="No live verified-source execution was available for this deployed address. Returned the deterministic benchmark mapping instead.",
                        live_attempted=live_attempted,
                        source="deterministic-benchmark",
                    ),
                )
            return AuditExecutionResult(
                report=deterministic_result.report,
                execution=self.agent_forge.fallback_execution(
                    reason="No verified source could be retrieved for this deployed address and no live agent-forge execution result was produced. Upload a source bundle for deeper analysis.",
                    live_attempted=live_attempted,
                    source="safe-fallback",
                ),
            )

        if submission.input_kind == "source_bundle":
            live_attempted = submission.audit_id is not None
            if live_attempted:
                live_result = self.agent_forge.run_submission(submission)
                if live_result is not None:
                    return live_result
            deterministic_result = self.deterministic_backend.run_submission(submission)
            assert deterministic_result is not None
            if deterministic_result.report.benchmark_id != "source-bundle":
                return AuditExecutionResult(
                    report=deterministic_result.report,
                    execution=self.agent_forge.fallback_execution(
                        reason="No live agent-forge execution was available for this source bundle. Returned the deterministic benchmark mapping instead.",
                        live_attempted=live_attempted,
                        source="deterministic-benchmark",
                    ),
                )
            return AuditExecutionResult(
                report=deterministic_result.report,
                execution=self.agent_forge.fallback_execution(
                    reason="No deterministic benchmark matched this source bundle and no live agent-forge execution result was produced.",
                    live_attempted=live_attempted,
                    source="safe-fallback",
                ),
            )

        if submission.input_kind == "repository_url":
            if submission.audit_id is None:
                raise ValueError("audit_id is required for repository_url submissions")
            try:
                live_result = self.agent_forge.run_submission(submission)
            except AgentForgeExecutionError:
                raise
            if live_result is not None:
                return live_result
            if self.runtime.mode == "agent_forge":
                raise AgentForgeExecutionError(
                    "repository_url submissions require a local repository path or file:// URL when worker mode is agent_forge"
                )
            deterministic_result = self.deterministic_backend.run_submission(submission)
            assert deterministic_result is not None
            return AuditExecutionResult(
                report=deterministic_result.report,
                execution=self.agent_forge.fallback_execution(
                    reason="Repository submissions use the live agent-forge path only when a local repository checkout is available.",
                    live_attempted=True,
                    source="safe-fallback",
                ),
            )

        result = self.deterministic_backend.run_submission(submission)
        assert result is not None
        return result
