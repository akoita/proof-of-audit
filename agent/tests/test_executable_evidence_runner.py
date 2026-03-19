import io
import json
import subprocess
import tempfile
import zipfile
from pathlib import Path

from proof_of_audit_agent.challenge_verifier import EvidenceContext
from proof_of_audit_agent.executable_evidence_resolver import ExecutableEvidenceResolver
from proof_of_audit_agent.executable_evidence_runner import ExecutableEvidenceRunner


def test_runner_rejects_manifest_entrypoint_mismatch() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        source_path = Path(tmpdir) / "ChallengeEvidence.t.sol"
        source_path.write_text("contract ChallengeEvidenceTest {}", encoding="utf-8")
        runner = ExecutableEvidenceRunner()

        result = runner.run(
            EvidenceContext(
                proof_uri=source_path.as_uri(),
                benchmark_id=None,
                target_contract="0x1000000000000000000000000000000000000001",
                published_report={},
                evidence_type="executable_test",
                execution_env="foundry",
                evidence_manifest={
                    "bundle_format": "proof-of-audit-executable-evidence/v1",
                    "execution_env": "foundry",
                    "entrypoint": "test/OtherEvidence.t.sol",
                    "target_chain_id": 31337,
                },
                chain_id=31337,
                rpc_url="http://127.0.0.1:8545",
            )
        )

        assert result.outcome == "invalid_evidence"
        assert "entrypoint" in result.detail.lower()


def test_runner_uses_manifest_pinned_block_number() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        source_path = Path(tmpdir) / "ChallengeEvidence.t.sol"
        source_path.write_text("contract ChallengeEvidenceTest {}", encoding="utf-8")
        captured: dict[str, object] = {}

        def executor(command, **kwargs):  # type: ignore[no-untyped-def]
            captured["command"] = command
            captured["kwargs"] = kwargs
            return subprocess.CompletedProcess(command, 0, "ok", "")

        runner = ExecutableEvidenceRunner(executor=executor)

        result = runner.run(
            EvidenceContext(
                proof_uri=source_path.as_uri(),
                benchmark_id=None,
                target_contract="0x1000000000000000000000000000000000000001",
                published_report={},
                evidence_type="executable_test",
                execution_env="foundry",
                evidence_manifest={
                    "bundle_format": "proof-of-audit-executable-evidence/v1",
                    "execution_env": "foundry",
                    "entrypoint": "ChallengeEvidence.t.sol",
                    "target_chain_id": 31337,
                    "pinned_block_number": 424242,
                },
                chain_id=31337,
                rpc_url="http://127.0.0.1:8545",
            )
        )

        assert result.outcome == "passed"
        command = captured["command"]
        assert "--fork-block-number" in command
        block_index = command.index("--fork-block-number")
        assert command[block_index + 1] == "424242"


def test_runner_fetches_ipfs_evidence_before_execution() -> None:
    captured: dict[str, object] = {}
    payload = b"contract ChallengeEvidenceTest {}\n"

    class FakeResponse:
        def __init__(self, data: bytes) -> None:
            self.data = data
            self.offset = 0

        def read(self, size: int = -1) -> bytes:
            if size < 0:
                size = len(self.data) - self.offset
            chunk = self.data[self.offset : self.offset + size]
            self.offset += len(chunk)
            return chunk

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            del exc_type, exc, tb

    def urlopen(req, timeout):  # type: ignore[no-untyped-def]
        assert req.full_url == "https://gateway.example/ipfs/QmRemote/ChallengeEvidence.t.sol"
        assert timeout == 15
        return FakeResponse(payload)

    def executor(command, **kwargs):  # type: ignore[no-untyped-def]
        captured["command"] = command
        captured["cwd"] = kwargs["cwd"]
        local_test_path = Path(command[command.index("--match-path") + 1])
        assert local_test_path.is_file()
        assert local_test_path.read_text(encoding="utf-8") == payload.decode("utf-8")
        return subprocess.CompletedProcess(command, 0, "ok", "")

    runner = ExecutableEvidenceRunner(
        executor=executor,
        resolver=ExecutableEvidenceResolver(
            ipfs_gateway="https://gateway.example/ipfs",
            urlopen=urlopen,
        ),
    )

    result = runner.run(
        EvidenceContext(
            proof_uri="ipfs://QmRemote/ChallengeEvidence.t.sol",
            benchmark_id=None,
            target_contract="0x1000000000000000000000000000000000000001",
            published_report={},
            evidence_type="executable_test",
            execution_env="foundry",
            evidence_manifest={
                "bundle_format": "proof-of-audit-executable-evidence/v1",
                "execution_env": "foundry",
                "entrypoint": "ChallengeEvidence.t.sol",
                "target_chain_id": 31337,
                "pinned_block_number": 42,
            },
            chain_id=31337,
            rpc_url="http://127.0.0.1:8545",
        )
    )

    assert result.outcome == "passed"
    command = captured["command"]
    assert "--match-path" in command


def test_runner_rejects_evidence_hash_mismatch_before_execution() -> None:
    captured = {"called": False}
    payload = b"contract ChallengeEvidenceTest {}\n"

    class FakeResponse:
        def __init__(self, data: bytes) -> None:
            self.data = data
            self.offset = 0

        def read(self, size: int = -1) -> bytes:
            if size < 0:
                size = len(self.data) - self.offset
            chunk = self.data[self.offset : self.offset + size]
            self.offset += len(chunk)
            return chunk

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            del exc_type, exc, tb

    def urlopen(req, timeout):  # type: ignore[no-untyped-def]
        del timeout
        assert req.full_url == "https://gateway.example/ipfs/QmRemote/ChallengeEvidence.t.sol"
        return FakeResponse(payload)

    def executor(command, **kwargs):  # type: ignore[no-untyped-def]
        del command, kwargs
        captured["called"] = True
        return subprocess.CompletedProcess([], 0, "ok", "")

    runner = ExecutableEvidenceRunner(
        executor=executor,
        resolver=ExecutableEvidenceResolver(
            ipfs_gateway="https://gateway.example/ipfs",
            urlopen=urlopen,
        ),
    )

    result = runner.run(
        EvidenceContext(
            proof_uri="ipfs://QmRemote/ChallengeEvidence.t.sol",
            benchmark_id=None,
            target_contract="0x1000000000000000000000000000000000000001",
            published_report={},
            evidence_type="executable_test",
            execution_env="foundry",
            evidence_manifest={
                "bundle_format": "proof-of-audit-executable-evidence/v1",
                "execution_env": "foundry",
                "entrypoint": "ChallengeEvidence.t.sol",
                "target_chain_id": 31337,
                "pinned_block_number": 42,
            },
            chain_id=31337,
            rpc_url="http://127.0.0.1:8545",
            committed_evidence_hash="0x" + "11" * 32,
        )
    )

    assert result.outcome == "invalid_evidence"
    assert "committed on-chain hash" in result.summary.lower()
    assert captured["called"] is False


def test_runner_executes_wrapped_bundle_with_helper_contracts() -> None:
    captured: dict[str, object] = {}
    archive = io.BytesIO()
    manifest = {
        "bundle_format": "proof-of-audit-executable-evidence/v1",
        "execution_env": "foundry",
        "entrypoint": "test/ChallengeEvidence.t.sol",
        "target_chain_id": 31337,
        "test_contract": "ChallengeEvidenceTest",
        "pinned_block_number": 42,
    }
    test_source = (
        'import "../src/Helper.sol";\n'
        "contract ChallengeEvidenceTest is Helper {}\n"
    )
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("challenge-bundle/manifest.json", json.dumps(manifest))
        bundle.writestr("challenge-bundle/test/ChallengeEvidence.t.sol", test_source)
        bundle.writestr(
            "challenge-bundle/src/Helper.sol",
            "contract Helper {}\n",
        )

    class FakeResponse:
        def __init__(self, data: bytes) -> None:
            self.data = data
            self.offset = 0

        def read(self, size: int = -1) -> bytes:
            if size < 0:
                size = len(self.data) - self.offset
            chunk = self.data[self.offset : self.offset + size]
            self.offset += len(chunk)
            return chunk

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            del exc_type, exc, tb

    def urlopen(req, timeout):  # type: ignore[no-untyped-def]
        assert req.full_url == "https://gateway.example/ipfs/QmBundle/challenge-bundle.zip"
        assert timeout == 15
        return FakeResponse(archive.getvalue())

    def executor(command, **kwargs):  # type: ignore[no-untyped-def]
        captured["command"] = command
        root = Path(kwargs["cwd"])
        local_test_path = Path(command[command.index("--match-path") + 1])
        assert local_test_path == root / "test/ChallengeEvidence.t.sol"
        assert local_test_path.read_text(encoding="utf-8") == test_source
        assert (root / "src/Helper.sol").read_text(encoding="utf-8") == "contract Helper {}\n"
        return subprocess.CompletedProcess(command, 0, "ok", "")

    runner = ExecutableEvidenceRunner(
        forge_bin="true",
        executor=executor,
        resolver=ExecutableEvidenceResolver(
            ipfs_gateway="https://gateway.example/ipfs",
            urlopen=urlopen,
        ),
    )

    result = runner.run(
        EvidenceContext(
            proof_uri="ipfs://QmBundle/challenge-bundle.zip",
            benchmark_id=None,
            target_contract="0x1000000000000000000000000000000000000001",
            published_report={},
            evidence_type="executable_test",
            execution_env="foundry",
            evidence_manifest=manifest,
            chain_id=31337,
            rpc_url="http://127.0.0.1:8545",
        )
    )

    assert result.outcome == "passed"
    command = captured["command"]
    assert "--match-path" in command
    assert "--match-contract" in command
    contract_index = command.index("--match-contract")
    assert command[contract_index + 1] == "^ChallengeEvidenceTest$"
