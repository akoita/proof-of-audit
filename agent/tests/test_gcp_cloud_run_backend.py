import base64
import json
from pathlib import Path
import zipfile

import pytest

from proof_of_audit_agent.backends.gcp_cloud_run import GCPCloudRunBackend


class FakeResponse:
    def __init__(self, payload: str) -> None:
        self._payload = payload.encode("utf-8")

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        del exc_type, exc, tb


def test_gcp_cloud_run_backend_posts_archived_evidence_and_returns_result(
    tmp_path: Path,
) -> None:
    evidence_file = tmp_path / "test" / "ChallengeEvidence.t.sol"
    evidence_file.parent.mkdir(parents=True, exist_ok=True)
    evidence_file.write_text("contract ChallengeEvidenceTest {}\n", encoding="utf-8")
    captured: dict[str, object] = {}

    def urlopen(req, timeout):  # type: ignore[no-untyped-def]
        captured["url"] = req.full_url
        captured["headers"] = dict(req.header_items())
        captured["timeout"] = timeout
        captured["payload"] = json.loads(req.data.decode("utf-8"))
        return FakeResponse(json.dumps({"returncode": 0, "stdout": "ok", "stderr": ""}))

    backend = GCPCloudRunBackend(
        service_url="https://runner.example/execute",
        bearer_token="test-token",
        urlopen=urlopen,
    )

    result = backend.execute(
        command=[
            "forge",
            "test",
            "--root",
            str(tmp_path),
            "--match-path",
            str(evidence_file),
            "--fork-url",
            "https://rpc.example",
            "--fork-block-number",
            "42",
            "--gas-limit",
            "30000000",
            "--no-ffi",
            "-vv",
        ],
        cwd=tmp_path,
        env={
            "HOME": str(tmp_path / ".home"),
            "USER": "proof-of-audit",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "FOUNDRY_DISABLE_NIGHTLY_WARNING": "1",
            "FOUNDRY_DISABLE_TELEMETRY": "1",
        },
        timeout_seconds=60,
        memory_limit_bytes=512 * 1024 * 1024,
    )

    payload = captured["payload"]
    headers = {key.lower(): value for key, value in captured["headers"].items()}
    assert captured["url"] == "https://runner.example/execute"
    assert captured["timeout"] == 65
    assert headers["authorization"] == "Bearer test-token"
    assert payload["working_directory"] == "/workspace"
    assert payload["command"][0] == "forge"
    assert payload["command"][payload["command"].index("--root") + 1] == "/workspace"
    assert (
        payload["command"][payload["command"].index("--match-path") + 1]
        == "/workspace/test/ChallengeEvidence.t.sol"
    )
    archive_bytes = base64.b64decode(payload["archive_base64"].encode("ascii"))
    archive_path = tmp_path / "archive.zip"
    archive_path.write_bytes(archive_bytes)
    with zipfile.ZipFile(archive_path) as archive:
        assert archive.read("test/ChallengeEvidence.t.sol").decode("utf-8").startswith(
            "contract ChallengeEvidenceTest"
        )
    assert result.backend == "gcp_cloud_run"
    assert result.isolation_level == "cloud"
    assert result.stdout == "ok"


def test_gcp_cloud_run_backend_fetches_identity_token_from_metadata(
    tmp_path: Path,
) -> None:
    evidence_file = tmp_path / "ChallengeEvidence.t.sol"
    evidence_file.write_text("contract ChallengeEvidenceTest {}\n", encoding="utf-8")
    seen: list[tuple[str, dict[str, str]]] = []

    def metadata_urlopen(req, timeout):  # type: ignore[no-untyped-def]
        del timeout
        seen.append((req.full_url, dict(req.header_items())))
        return FakeResponse("metadata-token")

    def service_urlopen(req, timeout):  # type: ignore[no-untyped-def]
        del timeout
        seen.append((req.full_url, dict(req.header_items())))
        return FakeResponse(json.dumps({"returncode": 1, "stdout": "", "stderr": "boom"}))

    backend = GCPCloudRunBackend(
        service_url="https://runner.example/execute",
        audience="https://runner.example",
        urlopen=service_urlopen,
        metadata_urlopen=metadata_urlopen,
    )

    result = backend.execute(
        command=["forge", "test", "--root", str(tmp_path)],
        cwd=tmp_path,
        env={},
        timeout_seconds=30,
        memory_limit_bytes=128 * 1024 * 1024,
    )

    assert "audience=https%3A%2F%2Frunner.example" in seen[0][0]
    metadata_headers = {key.lower(): value for key, value in seen[0][1].items()}
    service_headers = {key.lower(): value for key, value in seen[1][1].items()}
    assert metadata_headers["metadata-flavor"] == "Google"
    assert service_headers["authorization"] == "Bearer metadata-token"
    assert result.returncode == 1
    assert result.stderr == "boom"


def test_gcp_cloud_run_backend_rejects_missing_response_fields(tmp_path: Path) -> None:
    evidence_file = tmp_path / "ChallengeEvidence.t.sol"
    evidence_file.write_text("contract ChallengeEvidenceTest {}\n", encoding="utf-8")

    def urlopen(req, timeout):  # type: ignore[no-untyped-def]
        del req, timeout
        return FakeResponse(json.dumps({"stdout": "ok", "stderr": ""}))

    backend = GCPCloudRunBackend(
        service_url="https://runner.example/execute",
        bearer_token="test-token",
        urlopen=urlopen,
    )

    with pytest.raises(OSError, match="returncode"):
        backend.execute(
            command=["forge", "test", "--root", str(tmp_path)],
            cwd=tmp_path,
            env={},
            timeout_seconds=30,
            memory_limit_bytes=128 * 1024 * 1024,
        )
