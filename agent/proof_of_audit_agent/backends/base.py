from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class EvidenceExecutionResult:
    returncode: int
    stdout: str
    stderr: str
    backend: str
    isolation_level: str


class EvidenceExecutionBackend(Protocol):
    @property
    def backend_name(self) -> str: ...

    @property
    def isolation_level(self) -> str: ...

    def is_available(self) -> bool: ...

    def execute(
        self,
        *,
        command: list[str],
        cwd: Path,
        env: dict[str, str],
        timeout_seconds: int,
        memory_limit_bytes: int,
    ) -> EvidenceExecutionResult: ...
