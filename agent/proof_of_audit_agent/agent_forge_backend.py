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

from proof_of_audit_agent.agent_forge_service_client import AgentForgeServiceClient
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
    command: str = "python -m proof_of_audit_agent.agent_forge_cli"
    provider: str | None = None
    model: str | None = None
    max_iterations: int | None = None
    runs_home: Path | None = None
    service_base_url: str | None = None
    service_api_token: str | None = None
    service_profile_id: str = "proof-of-audit-solidity-v1"
    service_report_schema: str = "proof-of-audit-report-v1"
    service_poll_interval_seconds: float = 0.25
    service_poll_timeout_seconds: float = 60.0
    service_request_timeout_seconds: float = 30.0
    service_source_storage_kind: str = "local"
    service_source_gcs_bucket: str | None = None
    service_source_gcs_prefix: str = "source-bundles"
    service_source_ipfs_api_url: str | None = None
    service_source_ipfs_auth_header: str | None = None
    sourcify_base_url: str = DEFAULT_SOURCIFY_BASE_URL
    explorer_api_url: str | None = DEFAULT_EXPLORER_API_URL
    explorer_api_key: str | None = None
    enabled_input_kinds: tuple[str, ...] = DEFAULT_SUPPORTED_INPUT_KINDS
    detectors: tuple[str, ...] | None = None
    audit_profile: str | None = None

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

    @property
    def hosted_service_enabled(self) -> bool:
        return bool(self.service_base_url)


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
        self._last_error_message: str | None = None
        self.deployed_address_source_resolver = DeployedAddressSourceResolver(
            sourcify_base_url=runtime.sourcify_base_url,
            explorer_api_url=runtime.explorer_api_url,
            explorer_api_key=runtime.explorer_api_key,
        )
        self.service_client = (
            AgentForgeServiceClient(
                base_url=runtime.service_base_url,
                api_token=runtime.service_api_token,
                request_timeout_seconds=runtime.service_request_timeout_seconds,
                poll_interval_seconds=runtime.service_poll_interval_seconds,
                poll_timeout_seconds=runtime.service_poll_timeout_seconds,
            )
            if runtime.service_base_url
            else None
        )

    @property
    def backend_name(self) -> str:
        return "agent_forge"

    @property
    def last_error_message(self) -> str | None:
        return self._last_error_message

    def run_submission(self, submission: AuditSubmission) -> AuditExecutionResult | None:
        self._last_error_message = None
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

            if submission.audit_id is None:
                raise AgentForgeExecutionError("agent-forge submissions require an audit_id")
            task_prompt = self._build_task_prompt(entry_contract=effective_entry_contract)
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
            if self.service_client is not None:
                archive_path, source_digest = self._prepare_service_source_archive(
                    submission.audit_id,
                    source_path,
                )
                source_uri = self._store_service_source_archive(
                    submission.audit_id,
                    archive_path,
                )
                remote_result = self.service_client.run(
                    payload=self._build_service_request(
                        submission=submission,
                        source_uri=source_uri,
                        entry_contract=effective_entry_contract,
                        source_digest=source_digest,
                    )
                )
                report = self._load_hosted_service_report(
                    remote_result.report_payload,
                    source_path=source_path,
                    entry_contract=effective_entry_contract,
                    contract_address=submission.contract_address,
                )
                logs_payload = remote_result.logs_payload or {}
                artifacts = logs_payload.get("artifacts")
                run_dir = (
                    str(artifacts.get("run_dir"))
                    if isinstance(artifacts, dict) and artifacts.get("run_dir")
                    else None
                )
                execution = AuditExecution(
                    backend=self.backend_name,
                    mode=self.runtime.mode,
                    status="completed",
                    source="agent_forge_service",
                    live_attempted=True,
                    fallback_used=False,
                    task_prompt=task_prompt,
                    workspace_dir=str(archive_path.parent),
                    source_path=execution_source_path,
                    report_path=remote_result.report_url,
                    run_id=remote_result.run_id,
                    run_dir=run_dir,
                    status_url=remote_result.status_url,
                    logs_url=remote_result.logs_url,
                    source_digest=source_digest,
                    profile_id=self.runtime.service_profile_id,
                    provider=self.runtime.provider,
                    model=self.runtime.model,
                )
                return AuditExecutionResult(report=report, execution=execution)

            command = shlex.split(self.runtime.command)
            if not command:
                raise AgentForgeExecutionError("agent-forge command is not configured")
            workspace_dir = self._prepare_workspace(submission.audit_id, source_path)
            report_path = workspace_dir / REPORT_FILE
            before_runs = self._snapshot_runs()

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
                profile_id=self.runtime.audit_profile,
                detectors=list(self.runtime.detectors) if self.runtime.detectors else None,
            )
            return AuditExecutionResult(report=report, execution=execution)
        except Exception as exc:
            self._last_error_message = self._describe_live_failure(exc, submission)
            if self.runtime.strict_live_mode:
                raise AgentForgeExecutionError(self._last_error_message) from exc
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

    def _describe_live_failure(
        self,
        exc: Exception,
        submission: AuditSubmission,
    ) -> str:
        message = str(exc).strip() or "live agent-forge execution failed"
        if (
            submission.input_kind == "deployed_address"
            and "No verified source was available for this deployed address." in message
            and not self.runtime.explorer_api_key
        ):
            return (
                f"{message} Explorer API credentials are not configured on this API instance, "
                "so explorer-backed verified-source lookup is unavailable."
            )
        if (
            submission.input_kind == "deployed_address"
            and not self.runtime.hosted_service_enabled
            and self.runtime.mode in {"hybrid", "agent_forge"}
        ):
            return (
                f"{message} No hosted agent-forge service URL is configured on this API instance; "
                "it can only rely on local command execution for live analysis."
            )
        return message

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

    def _prepare_service_source_archive(
        self,
        audit_id: str,
        source_path: Path,
    ) -> tuple[Path, str]:
        target_root = self.workspace_root / "agent-forge-service" / audit_id
        if target_root.exists():
            shutil.rmtree(target_root)
        target_root.mkdir(parents=True, exist_ok=True)
        archive_path = target_root / "source.zip"
        if source_path.is_file() and source_path.suffix.lower() == ".zip":
            shutil.copy2(source_path, archive_path)
        else:
            with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                if source_path.is_dir():
                    for item in sorted(source_path.rglob("*")):
                        if item.is_dir():
                            continue
                        archive.write(item, arcname=str(item.relative_to(source_path)))
                else:
                    archive.write(source_path, arcname=source_path.name)
        digest = sha256(archive_path.read_bytes()).hexdigest()
        return archive_path, f"sha256:{digest}"

    def _store_service_source_archive(self, audit_id: str, archive_path: Path) -> str:
        try:
            from proof_of_audit_api.source_bundle_storage import (
                SourceBundleStorageError,
                build_source_bundle_storage,
            )
        except ImportError as exc:
            raise AgentForgeExecutionError(
                "hosted agent-forge source upload requires proof_of_audit_api.source_bundle_storage"
            ) from exc

        env = {
            "PROOF_OF_AUDIT_SOURCE_BUNDLE_STORAGE_KIND": self.runtime.service_source_storage_kind,
        }
        if self.runtime.service_source_gcs_bucket:
            env["PROOF_OF_AUDIT_SOURCE_BUNDLE_GCS_BUCKET"] = self.runtime.service_source_gcs_bucket
        if self.runtime.service_source_gcs_prefix:
            env["PROOF_OF_AUDIT_SOURCE_BUNDLE_GCS_PREFIX"] = self.runtime.service_source_gcs_prefix
        if self.runtime.service_source_ipfs_api_url:
            env["PROOF_OF_AUDIT_SOURCE_BUNDLE_IPFS_API_URL"] = (
                self.runtime.service_source_ipfs_api_url
            )
        if self.runtime.service_source_ipfs_auth_header:
            env["PROOF_OF_AUDIT_SOURCE_BUNDLE_IPFS_AUTH_HEADER"] = (
                self.runtime.service_source_ipfs_auth_header
            )
        try:
            storage = build_source_bundle_storage(
                workspace_root=self.workspace_root,
                env=env,
            )
        except SourceBundleStorageError as exc:
            raise AgentForgeExecutionError(
                f"hosted agent-forge source upload is misconfigured: {exc}"
            ) from exc
        if getattr(storage, "storage_backend", "local") == "local":
            raise AgentForgeExecutionError(
                "hosted agent-forge service requires non-local source bundle storage; configure GCS or IPFS storage"
            )
        try:
            stored = storage.store(
                original_filename=f"{audit_id}.zip",
                content=archive_path.read_bytes(),
            )
        except SourceBundleStorageError as exc:
            raise AgentForgeExecutionError(
                f"hosted agent-forge source upload failed: {exc}"
            ) from exc
        return stored.source_bundle_uri

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
        if self.runtime.detectors:
            invocation.extend(["--detectors", ",".join(self.runtime.detectors)])
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
        seen_ids: set[str] = set()
        for index, raw_finding in enumerate(payload.get("findings", []), start=1):
            title = str(raw_finding.get("title") or f"Finding {index}")
            detector = str(raw_finding.get("detector") or "agent_forge.llm")
            category = str(raw_finding.get("category") or "other")
            raw_id = raw_finding.get("finding_id")
            if raw_id:
                finding_id = str(raw_id)
                # Deduplicate even explicit IDs
                candidate = finding_id
                counter = 2
                while candidate in seen_ids:
                    candidate = f"{finding_id}-{counter}"
                    counter += 1
                finding_id = candidate
                seen_ids.add(finding_id)
            else:
                finding_id = self._finding_id(
                    category=category,
                    detector=detector,
                    title=title,
                    index=index,
                    seen=seen_ids,
                )
            findings.append(
                Finding(
                    finding_id=finding_id,
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

    def _load_hosted_service_report(
        self,
        payload: dict[str, object],
        *,
        source_path: Path,
        entry_contract: str | None,
        contract_address: str | None,
    ) -> AuditReport:
        target = payload.get("target")
        report_contract_address = contract_address
        if report_contract_address is None and isinstance(target, dict):
            resolved_address = self._optional_string(target.get("contract_address"))
            if resolved_address is not None:
                report_contract_address = resolved_address
        workspace_dir = source_path if source_path.is_dir() else source_path.parent
        return self._load_report(
            report_path=self._write_hosted_report_cache(payload),
            workspace_dir=workspace_dir,
            source_path=source_path,
            entry_contract=entry_contract,
            contract_address=report_contract_address,
        )

    def _write_hosted_report_cache(self, payload: dict[str, object]) -> Path:
        cache_root = self.workspace_root / "agent-forge-service-report-cache"
        cache_root.mkdir(parents=True, exist_ok=True)
        digest = sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
        path = cache_root / f"{digest}.json"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    def _build_service_request(
        self,
        *,
        submission: AuditSubmission,
        source_uri: str,
        entry_contract: str | None,
        source_digest: str,
    ) -> dict[str, object]:
        return {
            "schema_version": "agent-forge-run-request-v1",
            "client": {
                "name": "proof-of-audit",
                "request_id": submission.audit_id,
                "service_id": "proof-of-audit-auditor",
            },
            "profile": {
                "id": self.runtime.service_profile_id,
                "report_schema": self.runtime.service_report_schema,
                "max_iterations": self.runtime.max_iterations,
            },
            "source": {
                "kind": "archive_uri",
                "uri": source_uri,
                "archive_format": "zip",
                "entry_contract": entry_contract,
                "source_digest": source_digest,
            },
            "target": {
                "submission_kind": submission.input_kind,
                "network": submission.network,
                "chain_id": submission.chain_id,
                "contract_address": submission.contract_address,
            },
            "artifacts": {
                "result_delivery": "pull",
                "include_logs": True,
            },
        }

    def _build_task_prompt(self, *, entry_contract: str | None) -> str:
        entry_clause = (
            f"Focus first on the contract named {entry_contract}. " if entry_contract else ""
        )
        detectors = self.runtime.detectors
        if detectors and tuple(detectors) != ("*",):
            families = ", ".join(d.replace("_", " ") for d in detectors)
            scope_clause = f"Focus ONLY on these vulnerability families: {families}. Ignore any other issue classes. "
        else:
            scope_clause = "Check for three issue classes: reentrancy, access control, and unchecked external calls. "
        profile_clause = (
            f"You are running as audit profile '{self.runtime.audit_profile}'. "
            if self.runtime.audit_profile
            else ""
        )
        return (
            f"{profile_clause}"
            f"Audit this smart contract repository. {scope_clause}"
            f"{entry_clause}"
            f"Do not modify the source code except for writing a JSON report to {REPORT_FILE}. "
            "Write valid JSON with the fields summary, confidence, optional benchmark_id, and findings. "
            "Each finding should include title, severity, category, description, impact, recommendation, confidence, "
            "optional affected_function, optional source_path, optional start_line, optional end_line, optional evidence_uri, and optional detector. "
            "If no finding is confirmed, write an empty findings array and explain the result in summary."
        )

    def _finding_id(
        self,
        *,
        category: str,
        detector: str,
        title: str,
        index: int,
        seen: set[str] | None = None,
    ) -> str:
        normalized_title = "-".join(title.lower().split()) or f"finding-{index}"
        normalized_detector = detector.replace(".", "-").replace("_", "-")
        base_id = f"agent-forge-live.{category}.{normalized_detector}.{normalized_title}"
        if seen is None:
            return base_id
        candidate = base_id
        counter = 2
        while candidate in seen:
            candidate = f"{base_id}-{counter}"
            counter += 1
        seen.add(candidate)
        return candidate

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
