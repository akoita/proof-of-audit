from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Callable
from urllib import error, request

from proof_of_audit_agent.challenge_verifier import EvidenceContext
from proof_of_audit_agent.executable_evidence_resolver import (
    EvidenceResolutionError,
    ExecutableEvidenceResolver,
)


RUNNER_NAME = "foundry-executable-evidence-v1"
DEFAULT_TIMEOUT_SECONDS = 60
DEFAULT_MEMORY_LIMIT_BYTES = 512 * 1024 * 1024
DEFAULT_GAS_LIMIT = 30_000_000


@dataclass(frozen=True)
class ExecutableEvidenceRunResult:
    outcome: str
    summary: str
    detail: str
    stdout: str = ""
    stderr: str = ""
    source_path: str | None = None
    source_text: str | None = None
    fork_block_number: int | None = None

    @property
    def execution_log(self) -> str:
        parts = []
        if self.stdout:
            parts.append(self.stdout)
        if self.stderr:
            parts.append(self.stderr)
        return "\n".join(parts).strip()


Executor = Callable[..., subprocess.CompletedProcess[str]]


class ExecutableEvidenceRunner:
    def __init__(
        self,
        *,
        forge_bin: str = "forge",
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        memory_limit_bytes: int = DEFAULT_MEMORY_LIMIT_BYTES,
        gas_limit: int = DEFAULT_GAS_LIMIT,
        executor: Executor | None = None,
        resolver: ExecutableEvidenceResolver | None = None,
    ) -> None:
        self.forge_bin = forge_bin
        self.timeout_seconds = timeout_seconds
        self.memory_limit_bytes = memory_limit_bytes
        self.gas_limit = gas_limit
        self._executor = executor or subprocess.run
        self.resolver = resolver or ExecutableEvidenceResolver()

    def run(self, context: EvidenceContext) -> ExecutableEvidenceRunResult:
        if context.execution_env != "foundry":
            return ExecutableEvidenceRunResult(
                outcome="invalid_evidence",
                summary="Executable evidence must declare the Foundry execution environment.",
                detail="Set execution_env to 'foundry' when submitting executable test evidence.",
            )
        if not context.rpc_url:
            return ExecutableEvidenceRunResult(
                outcome="runner_error",
                summary="Executable evidence requires a configured RPC URL.",
                detail="The advisory runner cannot fork chain state without PROOF_OF_AUDIT_RPC_URL or BASE_SEPOLIA_RPC_URL.",
            )
        try:
            resolved = self.resolver.resolve(context)
        except EvidenceResolutionError as exc:
            return ExecutableEvidenceRunResult(
                outcome="invalid_evidence",
                summary="Executable evidence could not be fetched or validated.",
                detail=str(exc),
            )
        with resolved:
            manifest = resolved.manifest
            source_path = resolved.source_path
            source_text = resolved.source_text
            if (
                context.committed_evidence_hash is not None
                and resolved.canonical_hash != context.committed_evidence_hash
            ):
                return ExecutableEvidenceRunResult(
                    outcome="invalid_evidence",
                    summary="Fetched executable evidence did not match the committed on-chain hash.",
                    detail="The materialized evidence bundle hash does not match the hash committed at challenge submission time.",
                    source_path=str(source_path),
                    source_text=source_text,
                )
            if shutil.which(self.forge_bin) is None:
                return ExecutableEvidenceRunResult(
                    outcome="runner_error",
                    summary="Foundry is not installed on this API host.",
                    detail="Install forge before enabling executable evidence verification.",
                    source_path=str(source_path),
                    source_text=source_text,
                )
            manifest_chain_id = manifest.get("target_chain_id")
            if isinstance(manifest_chain_id, int) and context.chain_id is not None:
                if manifest_chain_id != context.chain_id:
                    return ExecutableEvidenceRunResult(
                        outcome="invalid_evidence",
                        summary="Executable evidence manifest targets a different chain than the challenged audit.",
                        detail="The manifest target_chain_id must match the challenged audit chain_id for executable evidence.",
                        source_path=str(source_path),
                    )
            manifest_block_number = manifest.get("pinned_block_number")
            block_number = (
                manifest_block_number
                if isinstance(manifest_block_number, int)
                else self._fetch_block_number(context.rpc_url)
            )
            if block_number is None:
                return ExecutableEvidenceRunResult(
                    outcome="runner_error",
                    summary="Executable evidence runner could not pin a fork block number.",
                    detail="The runner requires a reachable fork RPC endpoint so it can execute against deterministic chain state.",
                    source_path=str(source_path),
                    source_text=source_text,
                )
            with tempfile.TemporaryDirectory(prefix="proof-of-audit-evidence-") as tmpdir:
                root = Path(tmpdir)
                if resolved.bundle_mode:
                    shutil.copytree(resolved.source_root, root, dirs_exist_ok=True)
                    local_test_path = root / source_path.relative_to(resolved.source_root)
                else:
                    test_dir = root / "test"
                    test_dir.mkdir(parents=True, exist_ok=True)
                    local_test_path = test_dir / source_path.name
                    local_test_path.write_text(source_text, encoding="utf-8")
                (root / "foundry.toml").write_text(
                    '[profile.default]\n'
                    'src = "src"\n'
                    'test = "test"\n'
                    "libs = []\n"
                    "ffi = false\n",
                    encoding="utf-8",
                )

                env = self._build_env(root)
                command = [
                    self.forge_bin,
                    "test",
                    "--root",
                    str(root),
                    "--match-path",
                    str(local_test_path),
                    "--fork-url",
                    context.rpc_url,
                    "--fork-block-number",
                    str(block_number),
                    "--gas-limit",
                    str(self.gas_limit),
                    "--no-ffi",
                    "-vv",
                ]
                contract_selector = self._contract_selector_from_manifest(manifest)
                if contract_selector is not None:
                    command.extend(["--match-contract", contract_selector])
                try:
                    result = self._executor(
                        command,
                        cwd=root,
                        env=env,
                        text=True,
                        capture_output=True,
                        timeout=self.timeout_seconds,
                        preexec_fn=self._build_preexec_fn(),
                        check=False,
                    )
                except subprocess.TimeoutExpired as exc:
                    return ExecutableEvidenceRunResult(
                        outcome="runner_error",
                        summary="Executable evidence timed out in the advisory runner.",
                        detail=f"Execution exceeded the {self.timeout_seconds}s limit.",
                        stdout=exc.stdout or "",
                        stderr=exc.stderr or "",
                        source_path=str(source_path),
                        source_text=source_text,
                        fork_block_number=block_number,
                    )
                except OSError as exc:
                    return ExecutableEvidenceRunResult(
                        outcome="runner_error",
                        summary="Executable evidence runner failed to start Foundry.",
                        detail=str(exc),
                        source_path=str(source_path),
                        source_text=source_text,
                        fork_block_number=block_number,
                    )

        outcome = "passed" if result.returncode == 0 else "failed"
        return ExecutableEvidenceRunResult(
            outcome=outcome,
            summary=(
                "Executable evidence passed against the forked chain state."
                if result.returncode == 0
                else "Executable evidence did not pass against the forked chain state."
            ),
            detail=(
                "Foundry reported a successful test run for the submitted evidence."
                if result.returncode == 0
                else "Foundry reported a failing or reverting test run for the submitted evidence."
            ),
            stdout=result.stdout,
            stderr=result.stderr,
            source_path=str(source_path),
            source_text=source_text,
            fork_block_number=block_number,
        )

    def _fetch_block_number(self, rpc_url: str) -> int | None:
        payload = json.dumps(
            {
                "jsonrpc": "2.0",
                "method": "eth_blockNumber",
                "params": [],
                "id": 1,
            }
        ).encode("utf-8")
        req = request.Request(
            rpc_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=10) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (OSError, error.URLError, error.HTTPError, json.JSONDecodeError):
            return None
        result = body.get("result")
        if not isinstance(result, str):
            return None
        try:
            return int(result, 16)
        except ValueError:
            return None

    def _build_env(self, root: Path) -> dict[str, str]:
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(root / ".home"),
            "USER": "proof-of-audit",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "FOUNDRY_DISABLE_NIGHTLY_WARNING": "1",
            "FOUNDRY_DISABLE_TELEMETRY": "1",
        }
        (root / ".home").mkdir(parents=True, exist_ok=True)
        for key in (
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "NO_PROXY",
            "http_proxy",
            "https_proxy",
            "all_proxy",
            "no_proxy",
        ):
            env.pop(key, None)
        return env

    def _contract_selector_from_manifest(
        self, manifest: dict[str, object]
    ) -> str | None:
        test_contract = manifest.get("test_contract")
        if isinstance(test_contract, str) and test_contract:
            return f"^{test_contract}$"
        match_contract = manifest.get("match_contract")
        if isinstance(match_contract, str) and match_contract:
            return match_contract
        return None

    def _build_preexec_fn(self) -> Callable[[], None] | None:
        try:
            import resource
        except ImportError:
            return None

        def configure_limits() -> None:
            resource.setrlimit(
                resource.RLIMIT_AS,
                (self.memory_limit_bytes, self.memory_limit_bytes),
            )

        return configure_limits
