import subprocess
import tempfile
from pathlib import Path

from proof_of_audit_agent.backends.local_subprocess import LocalSubprocessBackend


def test_local_subprocess_backend_reports_metadata_and_result() -> None:
    captured: dict[str, object] = {}

    def executor(command, **kwargs):  # type: ignore[no-untyped-def]
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, "ok", "warn")

    backend = LocalSubprocessBackend(
        executable_name="true",
        executor=executor,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        result = backend.execute(
            command=["true", "--version"],
            cwd=Path(tmpdir),
            env={"PATH": ""},
            timeout_seconds=5,
            memory_limit_bytes=1024,
        )

    assert backend.is_available() is True
    assert result.returncode == 0
    assert result.stdout == "ok"
    assert result.stderr == "warn"
    assert result.backend == "local_subprocess"
    assert result.isolation_level == "process"
    assert captured["command"] == ["true", "--version"]
