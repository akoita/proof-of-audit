from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import zipfile

from proof_of_audit_agent.models import AuditReport, Finding


REPORT_FILE = ".proof-of-audit/agent-report.json"
DEFAULT_SUPPORTED_INPUT_KINDS = ("repository_url", "source_bundle")


@dataclass(frozen=True)
class AgentForgeRuntimeConfig:
    mode: str = "deterministic"
    command: str = "python -m agent_forge.cli"
    provider: str | None = None
    model: str | None = None
    max_iterations: int | None = None
    runs_home: Path | None = None
    enabled_input_kinds: tuple[str, ...] = DEFAULT_SUPPORTED_INPUT_KINDS

    @property
    def runs_dir(self) -> Path | None:
        if self.runs_home is None:
            return None
        return self.runs_home / ".agent-forge" / "runs"

    @property
    def live_enabled(self) -> bool:
        return self.mode in {"hybrid", "agent_forge"}

    @property
    def strict_live_mode(self) -> bool:
        return self.mode == "agent_forge"


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


class AgentForgeExecutionError(ValueError):
    """Raised when live execution is required but cannot complete."""


class AgentForgeBackend:
    def __init__(self, runtime: AgentForgeRuntimeConfig, workspace_root: Path) -> None:
        self.runtime = runtime
        self.workspace_root = workspace_root

    def run_submission(
        self,
        *,
        audit_id: str,
        input_kind: str,
        repository_url: str | None = None,
        source_bundle_uri: str | None = None,
        entry_contract: str | None = None,
    ) -> AuditExecutionResult | None:
        if not self.runtime.live_enabled:
            return None
        if input_kind not in self.runtime.enabled_input_kinds:
            if self.runtime.strict_live_mode:
                raise AgentForgeExecutionError(
                    f"agent-forge mode does not support {input_kind} submissions yet"
                )
            return None

        source_path = self._resolve_source_path(
            input_kind=input_kind,
            repository_url=repository_url,
            source_bundle_uri=source_bundle_uri,
        )
        if source_path is None:
            if self.runtime.strict_live_mode:
                raise AgentForgeExecutionError(
                    f"agent-forge mode requires a local repository path or file:// source for {input_kind} submissions"
                )
            return None

        command = shlex.split(self.runtime.command)
        if not command:
            raise AgentForgeExecutionError("agent-forge command is not configured")

        workspace_dir = self._prepare_workspace(audit_id, source_path)
        task_prompt = self._build_task_prompt(entry_contract=entry_contract)
        report_path = workspace_dir / REPORT_FILE
        before_runs = self._snapshot_runs()

        try:
            self._invoke(command, workspace_dir, task_prompt)
            report = self._load_report(
                report_path=report_path,
                workspace_dir=workspace_dir,
                source_path=source_path,
                entry_contract=entry_contract,
            )
        except Exception as exc:
            if self.runtime.strict_live_mode:
                raise AgentForgeExecutionError(str(exc)) from exc
            return None

        run_dir = self._detect_new_run(before_runs, workspace_dir)
        execution = AuditExecution(
            backend="agent_forge",
            mode=self.runtime.mode,
            status="completed",
            source="agent_forge_run",
            live_attempted=True,
            fallback_used=False,
            task_prompt=task_prompt,
            workspace_dir=str(workspace_dir),
            source_path=str(source_path),
            report_path=str(report_path),
            run_id=run_dir.name if run_dir is not None else None,
            run_dir=str(run_dir) if run_dir is not None else None,
            provider=self.runtime.provider,
            model=self.runtime.model,
        )
        return AuditExecutionResult(report=report, execution=execution)

    def fallback_execution(
        self,
        *,
        reason: str,
        live_attempted: bool,
        source: str,
    ) -> AuditExecution | None:
        if self.runtime.mode == "deterministic" and not live_attempted:
            return None
        return AuditExecution(
            backend="deterministic",
            mode=self.runtime.mode,
            status="fallback",
            source=source,
            live_attempted=live_attempted,
            fallback_used=True,
            error=reason,
        )

    def _snapshot_runs(self) -> set[Path]:
        runs_dir = self.runtime.runs_dir
        if runs_dir is None or not runs_dir.exists():
            return set()
        return {path for path in runs_dir.iterdir() if path.is_dir()}

    def _detect_new_run(self, before_runs: set[Path], workspace_dir: Path) -> Path | None:
        runs_dir = self.runtime.runs_dir
        if runs_dir is None or not runs_dir.exists():
            return None
        candidates = [path for path in runs_dir.iterdir() if path.is_dir() and path not in before_runs]
        if not candidates:
            candidates = [path for path in runs_dir.iterdir() if path.is_dir()]
        for candidate in sorted(candidates, key=lambda item: item.stat().st_mtime, reverse=True):
            run_json = candidate / "run.json"
            if not run_json.exists():
                continue
            try:
                payload = json.loads(run_json.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if str(payload.get("repo_path") or "") == str(workspace_dir):
                return candidate
        return None

    def _resolve_source_path(
        self,
        *,
        input_kind: str,
        repository_url: str | None,
        source_bundle_uri: str | None,
    ) -> Path | None:
        candidate = repository_url if input_kind == "repository_url" else source_bundle_uri
        if not candidate:
            return None
        if candidate.startswith("file://"):
            path = Path(candidate[7:])
        else:
            path = Path(candidate)
        if not path.is_absolute():
            path = path.resolve()
        if not path.exists():
            return None
        return path

    def _prepare_workspace(self, audit_id: str, source_path: Path) -> Path:
        target_root = self.workspace_root / "agent-forge" / audit_id
        workspace_dir = target_root / "repo"
        if target_root.exists():
            shutil.rmtree(target_root)
        target_root.mkdir(parents=True, exist_ok=True)
        if source_path.is_dir():
            shutil.copytree(source_path, workspace_dir)
        else:
            workspace_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(source_path) as archive:
                archive.extractall(workspace_dir)
            entries = [entry for entry in workspace_dir.iterdir()]
            if len(entries) == 1 and entries[0].is_dir():
                workspace_dir = entries[0]
        (workspace_dir / ".proof-of-audit").mkdir(parents=True, exist_ok=True)
        return workspace_dir

    def _invoke(self, command: list[str], workspace_dir: Path, task_prompt: str) -> None:
        env = os.environ.copy()
        if self.runtime.runs_home is not None:
            env["HOME"] = str(self.runtime.runs_home)
        invocation = [*command, "run", "--task", task_prompt, "--repo", str(workspace_dir)]
        if self.runtime.provider:
            invocation.extend(["--provider", self.runtime.provider])
        if self.runtime.model:
            invocation.extend(["--model", self.runtime.model])
        if self.runtime.max_iterations is not None:
            invocation.extend(["--max-iterations", str(self.runtime.max_iterations)])
        completed = subprocess.run(
            invocation,
            cwd=workspace_dir,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            message = completed.stderr.strip() or completed.stdout.strip() or "agent-forge run failed"
            raise AgentForgeExecutionError(message)

    def _load_report(
        self,
        *,
        report_path: Path,
        workspace_dir: Path,
        source_path: Path,
        entry_contract: str | None,
    ) -> AuditReport:
        if not report_path.exists():
            raise AgentForgeExecutionError(
                f"agent-forge completed without producing {REPORT_FILE}"
            )
        payload = json.loads(report_path.read_text(encoding="utf-8"))
        findings: list[Finding] = []
        for index, raw_finding in enumerate(payload.get("findings", []), start=1):
            title = str(raw_finding.get("title") or f"Finding {index}")
            detector = str(raw_finding.get("detector") or "agent_forge.llm")
            category = str(raw_finding.get("category") or "other")
            findings.append(
                Finding(
                    finding_id=str(
                        raw_finding.get("finding_id")
                        or self._finding_id(
                            category=category,
                            detector=detector,
                            title=title,
                            index=index,
                        )
                    ),
                    title=title,
                    severity=str(raw_finding.get("severity") or "medium"),
                    category=category,
                    description=str(raw_finding.get("description") or "Agent Forge reported a potential issue."),
                    impact=str(raw_finding.get("impact") or "Review the generated report for context."),
                    recommendation=str(raw_finding.get("recommendation") or "Inspect the affected code path and confirm whether the finding is actionable."),
                    detector=detector,
                    confidence=str(raw_finding.get("confidence") or "medium"),
                    affected_function=self._optional_string(raw_finding.get("affected_function")),
                    source_path=self._normalize_source_path(raw_finding.get("source_path"), workspace_dir=workspace_dir, source_path=source_path),
                    start_line=self._optional_int(raw_finding.get("start_line")),
                    end_line=self._optional_int(raw_finding.get("end_line")),
                    evidence_uri=self._optional_string(raw_finding.get("evidence_uri")),
                )
            )
        return AuditReport(
            benchmark_id=str(payload.get("benchmark_id") or "agent-forge-live"),
            contract_address=self._synthetic_contract_address(str(source_path), entry_contract=entry_contract),
            summary=str(payload.get("summary") or "Agent Forge completed a live audit pass."),
            findings=findings,
            confidence=str(payload.get("confidence") or "medium"),
        )

    def _build_task_prompt(self, *, entry_contract: str | None) -> str:
        entry_clause = (
            f"Focus first on the contract named {entry_contract}. " if entry_contract else ""
        )
        return (
            "Audit this smart contract repository for three issue classes: reentrancy, access control, and unchecked external calls. "
            f"{entry_clause}"
            f"Do not modify the source code except for writing a JSON report to {REPORT_FILE}. "
            "Write valid JSON with the fields summary, confidence, optional benchmark_id, and findings. "
            "Each finding should include title, severity, category, description, impact, recommendation, confidence, "
            "optional affected_function, optional source_path, optional start_line, optional end_line, optional evidence_uri, and optional detector. "
            "If no finding is confirmed, write an empty findings array and explain the result in summary."
        )

    def _finding_id(self, *, category: str, detector: str, title: str, index: int) -> str:
        normalized_title = "-".join(title.lower().split()) or f"finding-{index}"
        normalized_detector = detector.replace(".", "-").replace("_", "-")
        return f"agent-forge-live.{category}.{normalized_detector}.{normalized_title}"

    def _synthetic_contract_address(self, source_identifier: str, entry_contract: str | None) -> str:
        digest = sha256(f"{source_identifier}:{entry_contract or ''}".encode("utf-8")).hexdigest()
        return f"0x{digest[:40]}"

    def _normalize_source_path(
        self, raw_path: object, *, workspace_dir: Path, source_path: Path
    ) -> str | None:
        if raw_path is None:
            return None
        path = Path(str(raw_path))
        if path.is_absolute():
            try:
                return str(path.relative_to(workspace_dir))
            except ValueError:
                try:
                    return str(path.relative_to(source_path))
                except ValueError:
                    return str(path)
        return str(path)

    def _optional_string(self, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _optional_int(self, value: object) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
