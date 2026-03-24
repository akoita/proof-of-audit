from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
from urllib import parse, request
import zipfile

from proof_of_audit_agent.auditor_backend import (
    AuditExecution,
    AuditExecutionResult,
    AuditSubmission,
)
from proof_of_audit_agent.deployed_address_source_resolver import (
    DEFAULT_EXPLORER_API_URL,
    DEFAULT_SOURCIFY_BASE_URL,
    DeployedAddressSourceResolver,
)
from proof_of_audit_agent.models import AuditReport, Finding


REPORT_FILE = ".proof-of-audit/agent-report.json"
DEFAULT_SUPPORTED_INPUT_KINDS = ("deployed_address", "repository_url", "source_bundle")
DEFAULT_IPFS_GATEWAY = "https://ipfs.io/ipfs"
DEFAULT_DOWNLOAD_TIMEOUT_SECONDS = 15
DEFAULT_MAX_REMOTE_SOURCE_BYTES = 25 * 1024 * 1024
_DOWNLOAD_CHUNK_SIZE = 64 * 1024


@dataclass(frozen=True)
class AgentForgeRuntimeConfig:
    mode: str = "deterministic"
    command: str = "python -m agent_forge.cli"
    provider: str | None = None
    model: str | None = None
    max_iterations: int | None = None
    runs_home: Path | None = None
    sourcify_base_url: str = DEFAULT_SOURCIFY_BASE_URL
    explorer_api_url: str | None = DEFAULT_EXPLORER_API_URL
    explorer_api_key: str | None = None
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


class AgentForgeExecutionError(ValueError):
    """Raised when live execution is required but cannot complete."""


@dataclass
class DownloadedSource:
    path: Path
    tempdir: tempfile.TemporaryDirectory[str]
    source_identifier: str | None = None
    entry_contract: str | None = None

    def cleanup(self) -> None:
        self.tempdir.cleanup()


class AgentForgeBackend:
    def __init__(self, runtime: AgentForgeRuntimeConfig, workspace_root: Path) -> None:
        self.runtime = runtime
        self.workspace_root = workspace_root
        self.deployed_address_source_resolver = DeployedAddressSourceResolver(
            sourcify_base_url=runtime.sourcify_base_url,
            explorer_api_url=runtime.explorer_api_url,
            explorer_api_key=runtime.explorer_api_key,
        )

    @property
    def backend_name(self) -> str:
        return "agent_forge"

    def run_submission(self, submission: AuditSubmission) -> AuditExecutionResult | None:
        if not self.runtime.live_enabled:
            return None
        if submission.input_kind not in self.runtime.enabled_input_kinds:
            if self.runtime.strict_live_mode:
                raise AgentForgeExecutionError(
                    f"agent-forge mode does not support {submission.input_kind} submissions yet"
                )
            return None

        downloaded_source: DownloadedSource | None = None
        try:
            source_path: Path | None = None
            effective_entry_contract = submission.entry_contract
            if submission.input_kind == "deployed_address":
                downloaded_source = self._materialize_deployed_address_source(
                    chain_id=submission.chain_id,
                    contract_address=submission.contract_address,
                )
                source_path = downloaded_source.path
                effective_entry_contract = (
                    downloaded_source.entry_contract or effective_entry_contract
                )
            else:
                source_path = self._resolve_source_path(
                    input_kind=submission.input_kind,
                    repository_url=submission.repository_url,
                    source_bundle_uri=submission.source_bundle_uri,
                )
                if source_path is None:
                    downloaded_source = self._materialize_remote_source(
                        input_kind=submission.input_kind,
                        repository_url=submission.repository_url,
                        source_bundle_uri=submission.source_bundle_uri,
                    )
                    source_path = downloaded_source.path if downloaded_source is not None else None
            if source_path is None:
                if self.runtime.strict_live_mode:
                    raise AgentForgeExecutionError(
                        f"agent-forge mode requires verified source retrieval or a reachable local/ipfs/http/gs source for {submission.input_kind} submissions"
                    )
                return None

            command = shlex.split(self.runtime.command)
            if not command:
                raise AgentForgeExecutionError("agent-forge command is not configured")

            if submission.audit_id is None:
                raise AgentForgeExecutionError("agent-forge submissions require an audit_id")
            workspace_dir = self._prepare_workspace(submission.audit_id, source_path)
            task_prompt = self._build_task_prompt(entry_contract=effective_entry_contract)
            report_path = workspace_dir / REPORT_FILE
            before_runs = self._snapshot_runs()
            execution_source_path = (
                downloaded_source.source_identifier
                if downloaded_source is not None and downloaded_source.source_identifier
                else submission.contract_address
                if submission.input_kind == "deployed_address" and submission.contract_address
                else submission.repository_url
                if submission.input_kind == "repository_url" and submission.repository_url
                else submission.source_bundle_uri
                if downloaded_source is not None and submission.source_bundle_uri
                else str(source_path)
            )

            self._invoke(command, workspace_dir, task_prompt)
            report = self._load_report(
                report_path=report_path,
                workspace_dir=workspace_dir,
                source_path=source_path,
                entry_contract=effective_entry_contract,
                contract_address=submission.contract_address,
            )
            run_dir = self._detect_new_run(before_runs, workspace_dir)
            execution = AuditExecution(
                backend=self.backend_name,
                mode=self.runtime.mode,
                status="completed",
                source="agent_forge_run",
                live_attempted=True,
                fallback_used=False,
                task_prompt=task_prompt,
                workspace_dir=str(workspace_dir),
                source_path=execution_source_path,
                report_path=str(report_path),
                run_id=run_dir.name if run_dir is not None else None,
                run_dir=str(run_dir) if run_dir is not None else None,
                provider=self.runtime.provider,
                model=self.runtime.model,
            )
            return AuditExecutionResult(report=report, execution=execution)
        except Exception as exc:
            if self.runtime.strict_live_mode:
                raise AgentForgeExecutionError(str(exc)) from exc
            return None
        finally:
            if downloaded_source is not None:
                downloaded_source.cleanup()

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

    def _materialize_deployed_address_source(
        self,
        *,
        chain_id: int | None,
        contract_address: str | None,
    ) -> DownloadedSource:
        resolved = self.deployed_address_source_resolver.resolve(
            chain_id=chain_id,
            contract_address=contract_address,
        )
        return DownloadedSource(
            path=resolved.path,
            tempdir=resolved.tempdir,
            source_identifier=resolved.source_uri,
            entry_contract=resolved.entry_contract,
        )

    def _materialize_remote_source(
        self,
        *,
        input_kind: str,
        repository_url: str | None,
        source_bundle_uri: str | None,
    ) -> DownloadedSource | None:
        candidate = repository_url if input_kind == "repository_url" else source_bundle_uri
        if not candidate:
            return None
        parsed = parse.urlparse(candidate)
        if parsed.scheme not in {"http", "https", "ipfs", "gs"}:
            return None
        tempdir = tempfile.TemporaryDirectory(prefix="proof-of-audit-source-")
        destination = Path(tempdir.name) / self._suggest_filename(candidate)
        try:
            if parsed.scheme == "gs":
                self._download_gcs_uri(candidate, destination)
            else:
                self._download_remote_uri(candidate, destination)
        except Exception:
            tempdir.cleanup()
            raise
        return DownloadedSource(path=destination, tempdir=tempdir)

    def _download_remote_uri(self, uri: str, destination: Path) -> None:
        remote_url = self._translate_remote_uri(uri)
        req = request.Request(remote_url, method="GET")
        total = 0
        with request.urlopen(req, timeout=DEFAULT_DOWNLOAD_TIMEOUT_SECONDS) as response:
            with destination.open("wb") as handle:
                while True:
                    chunk = response.read(_DOWNLOAD_CHUNK_SIZE)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > DEFAULT_MAX_REMOTE_SOURCE_BYTES:
                        raise AgentForgeExecutionError(
                            "remote source download exceeded the maximum allowed size"
                        )
                    handle.write(chunk)
        if total == 0:
            raise AgentForgeExecutionError("remote source download was empty")

    def _download_gcs_uri(self, uri: str, destination: Path) -> None:
        try:
            from google.cloud import storage
        except ImportError as exc:
            raise AgentForgeExecutionError(
                "google-cloud-storage is required to fetch gs:// source bundles"
            ) from exc
        bucket_name, object_name = self._parse_gcs_uri(uri)
        payload = storage.Client().bucket(bucket_name).blob(object_name).download_as_bytes()
        if len(payload) > DEFAULT_MAX_REMOTE_SOURCE_BYTES:
            raise AgentForgeExecutionError(
                "remote source download exceeded the maximum allowed size"
            )
        if not payload:
            raise AgentForgeExecutionError("remote source download was empty")
        destination.write_bytes(payload)

    def _translate_remote_uri(self, uri: str) -> str:
        parsed = parse.urlparse(uri)
        if parsed.scheme == "ipfs":
            gateway = os.environ.get("PROOF_OF_AUDIT_IPFS_GATEWAY") or DEFAULT_IPFS_GATEWAY
            path = parsed.netloc + parsed.path
            return f"{gateway.rstrip('/')}/{path.lstrip('/')}"
        return uri

    def _suggest_filename(self, uri: str) -> str:
        parsed = parse.urlparse(uri)
        if parsed.scheme == "gs":
            name = Path(parsed.path).name
            return name or "source-bundle.bin"
        name = Path(parse.unquote(parsed.path)).name
        if name:
            return name
        if parsed.netloc:
            return parsed.netloc
        return "source-bundle.bin"

    def _parse_gcs_uri(self, uri: str) -> tuple[str, str]:
        parsed = parse.urlparse(uri)
        bucket_name = parsed.netloc.strip()
        object_name = parsed.path.lstrip("/")
        if parsed.scheme != "gs" or not bucket_name or not object_name:
            raise AgentForgeExecutionError("gs:// source bundle URIs must include bucket and object path")
        return bucket_name, object_name

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
            if source_path.suffix.lower() == ".zip":
                with zipfile.ZipFile(source_path) as archive:
                    archive.extractall(workspace_dir)
                entries = [entry for entry in workspace_dir.iterdir()]
                if len(entries) == 1 and entries[0].is_dir():
                    workspace_dir = entries[0]
            else:
                shutil.copy2(source_path, workspace_dir / source_path.name)
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
        contract_address: str | None,
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
            contract_address=contract_address
            or self._synthetic_contract_address(
                str(source_path), entry_contract=entry_contract
            ),
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
