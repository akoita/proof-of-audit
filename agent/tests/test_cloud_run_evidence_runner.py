import io
from pathlib import Path
import subprocess
import zipfile

import pytest

from proof_of_audit_agent.cloud_run_evidence_runner import (
    EvidenceExecutionRequestError,
    execute_payload,
)


class FakeBlob:
    def __init__(self, data: bytes) -> None:
        self._data = data
        self.generation: int | None = None

    def download_as_bytes(self) -> bytes:
        return self._data


class FakeBucket:
    def __init__(self, data: bytes) -> None:
        self._blob = FakeBlob(data)

    def blob(self, name: str) -> FakeBlob:
        self.last_blob_name = name
        return self._blob


class FakeStorageClient:
    def __init__(self, data: bytes) -> None:
        self._bucket = FakeBucket(data)

    def bucket(self, name: str) -> FakeBucket:
        self.last_bucket_name = name
        return self._bucket


def test_execute_payload_downloads_archive_from_gcs_and_runs_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, "w") as archive:
        archive.writestr("test/ChallengeEvidence.t.sol", "contract ChallengeEvidenceTest {}\n")

    fake_storage_client = FakeStorageClient(archive_buffer.getvalue())
    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):  # type: ignore[no-untyped-def]
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = execute_payload(
        {
            "command": [
                "forge",
                "test",
                "--root",
                "/workspace",
                "--match-path",
                "/workspace/test/ChallengeEvidence.t.sol",
            ],
            "env": {},
            "timeout_seconds": 30,
            "memory_limit_bytes": 128 * 1024 * 1024,
            "working_directory": "/workspace",
            "archive_format": "zip",
            "archive_gcs_uri": "gs://proof-of-audit-staging/evidence/archive.zip",
            "archive_generation": 42,
        },
        storage_client_factory=lambda: fake_storage_client,
    )

    assert result["returncode"] == 0
    assert fake_storage_client.last_bucket_name == "proof-of-audit-staging"
    assert fake_storage_client._bucket.last_blob_name == "evidence/archive.zip"
    assert fake_storage_client._bucket._blob.generation == 42
    command = captured["command"]
    assert command[0] == "forge"
    assert command[command.index("--root") + 1].endswith("workspace")
    assert command[command.index("--match-path") + 1].endswith(
        "workspace/test/ChallengeEvidence.t.sol"
    )


def test_execute_payload_rejects_missing_archive_source() -> None:
    with pytest.raises(EvidenceExecutionRequestError, match="archive_base64 or archive_gcs_uri"):
        execute_payload(
            {
                "command": ["forge", "test"],
                "env": {},
                "timeout_seconds": 30,
                "memory_limit_bytes": 128 * 1024 * 1024,
                "working_directory": "/workspace",
                "archive_format": "zip",
            }
        )
