from __future__ import annotations

import io
import json
import tempfile
import zipfile
from pathlib import Path

import pytest

from proof_of_audit_agent.challenge_verifier import EvidenceContext
from proof_of_audit_agent.executable_evidence_resolver import (
    EvidenceResolutionError,
    ExecutableEvidenceResolver,
)


class FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self._buffer = io.BytesIO(payload)

    def read(self, size: int = -1) -> bytes:
        return self._buffer.read(size)

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        del exc_type, exc, tb


def _context(uri: str, *, manifest: dict | None = None) -> EvidenceContext:
    return EvidenceContext(
        proof_uri=uri,
        benchmark_id=None,
        target_contract="0x1000000000000000000000000000000000000001",
        published_report={},
        evidence_type="executable_test",
        execution_env="foundry",
        evidence_manifest=manifest,
        chain_id=31337,
        rpc_url="http://127.0.0.1:8545",
    )


def test_resolver_downloads_ipfs_sol_file() -> None:
    payload = b"contract ChallengeEvidenceTest {}\n"

    def urlopen(req, timeout):  # type: ignore[no-untyped-def]
        assert req.full_url == "https://gateway.example/ipfs/QmTest/ChallengeEvidence.t.sol"
        assert timeout == 15
        return FakeResponse(payload)

    resolver = ExecutableEvidenceResolver(
        ipfs_gateway="https://gateway.example/ipfs",
        urlopen=urlopen,
    )

    with resolver.resolve(_context("ipfs://QmTest/ChallengeEvidence.t.sol")) as resolved:
        assert resolved.source_path.name == "ChallengeEvidence.t.sol"
        assert resolved.source_text == payload.decode("utf-8")
        assert resolved.source_path.is_file()
        assert resolved.materialized_root is not None


def test_resolver_rejects_oversized_download() -> None:
    payload = b"a" * 32

    def urlopen(req, timeout):  # type: ignore[no-untyped-def]
        del req, timeout
        return FakeResponse(payload)

    resolver = ExecutableEvidenceResolver(
        ipfs_gateway="https://gateway.example/ipfs",
        max_download_bytes=8,
        urlopen=urlopen,
    )

    with pytest.raises(EvidenceResolutionError, match="maximum allowed size"):
        resolver.resolve(_context("ipfs://QmTooLarge/ChallengeEvidence.t.sol"))


def test_resolver_rejects_zip_path_traversal() -> None:
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("../escape.sol", "contract Escape {}")

    def urlopen(req, timeout):  # type: ignore[no-untyped-def]
        del req, timeout
        return FakeResponse(archive.getvalue())

    resolver = ExecutableEvidenceResolver(
        ipfs_gateway="https://gateway.example/ipfs",
        urlopen=urlopen,
    )

    with pytest.raises(EvidenceResolutionError, match="parent-traversing"):
        resolver.resolve(_context("ipfs://QmBundle/challenge-bundle.zip"))


def test_resolver_extracts_zip_bundle_and_reads_manifest() -> None:
    archive = io.BytesIO()
    manifest = {
        "bundle_format": "proof-of-audit-executable-evidence/v1",
        "execution_env": "foundry",
        "entrypoint": "test/ChallengeEvidence.t.sol",
        "target_chain_id": 31337,
        "expected_file_hashes": {},
    }
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("manifest.json", json.dumps(manifest))
        bundle.writestr("test/ChallengeEvidence.t.sol", "contract ChallengeEvidenceTest {}\n")
        bundle.writestr("README.md", "bundle")

    def urlopen(req, timeout):  # type: ignore[no-untyped-def]
        del req, timeout
        return FakeResponse(archive.getvalue())

    resolver = ExecutableEvidenceResolver(
        ipfs_gateway="https://gateway.example/ipfs",
        urlopen=urlopen,
    )

    with resolver.resolve(_context("ipfs://QmBundle/challenge-bundle.zip")) as resolved:
        assert resolved.bundle_mode is True
        assert resolved.source_path.name == "ChallengeEvidence.t.sol"
        assert resolved.manifest["entrypoint"] == "test/ChallengeEvidence.t.sol"
        assert resolved.source_path.read_text(encoding="utf-8").startswith("contract")


def test_resolver_uses_nested_bundle_root_for_single_wrapped_directory() -> None:
    archive = io.BytesIO()
    manifest = {
        "bundle_format": "proof-of-audit-executable-evidence/v1",
        "execution_env": "foundry",
        "entrypoint": "test/ChallengeEvidence.t.sol",
        "target_chain_id": 31337,
    }
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("challenge-bundle/manifest.json", json.dumps(manifest))
        bundle.writestr(
            "challenge-bundle/test/ChallengeEvidence.t.sol",
            "contract ChallengeEvidenceTest {}\n",
        )
        bundle.writestr("challenge-bundle/src/Helper.sol", "contract Helper {}\n")

    def urlopen(req, timeout):  # type: ignore[no-untyped-def]
        del req, timeout
        return FakeResponse(archive.getvalue())

    resolver = ExecutableEvidenceResolver(
        ipfs_gateway="https://gateway.example/ipfs",
        urlopen=urlopen,
    )

    with resolver.resolve(_context("ipfs://QmBundle/wrapped-bundle.zip")) as resolved:
        assert resolved.bundle_mode is True
        assert resolved.source_root.name == "challenge-bundle"
        assert resolved.source_path == resolved.source_root / "test/ChallengeEvidence.t.sol"
        assert (resolved.source_root / "src/Helper.sol").is_file()
