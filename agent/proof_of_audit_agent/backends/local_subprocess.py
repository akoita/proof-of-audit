from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
from typing import Callable

from proof_of_audit_agent.backends.base import (
    EvidenceExecutionBackend,
    EvidenceExecutionResult,
)


Executor = Callable[..., subprocess.CompletedProcess[str]]


class LocalSubprocessBackend(EvidenceExecutionBackend):
    def __init__(
        self,
        *,
        executable_name: str = "forge",
        executor: Executor | None = None,
    ) -> None:
        self.executable_name = executable_name
        self._executor = executor or subprocess.run

    @property
    def backend_name(self) -> str:
        return "local_subprocess"

    @property
    def isolation_level(self) -> str:
        return "process"

    def is_available(self) -> bool:
        return shutil.which(self.executable_name) is not None

    def execute(
        self,
        *,
        command: list[str],
        cwd: Path,
        env: dict[str, str],
        timeout_seconds: int,
        memory_limit_bytes: int,
    ) -> EvidenceExecutionResult:
        result = self._executor(
            command,
            cwd=cwd,
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            preexec_fn=self._build_preexec_fn(memory_limit_bytes),
            check=False,
        )
        return EvidenceExecutionResult(
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            backend=self.backend_name,
            isolation_level=self.isolation_level,
        )

    def _build_preexec_fn(
        self, memory_limit_bytes: int
    ) -> Callable[[], None] | None:
        try:
            import resource
        except ImportError:
            return None

        def configure_limits() -> None:
            resource.setrlimit(
                resource.RLIMIT_AS,
                (memory_limit_bytes, memory_limit_bytes),
            )

        return configure_limits
