from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tarfile
import tempfile
from typing import Any, Callable
from urllib import parse, request
import zipfile

from proof_of_audit_agent.challenge_verifier import EvidenceContext


DEFAULT_IPFS_GATEWAY = "https://ipfs.io/ipfs"
DEFAULT_MAX_DOWNLOAD_BYTES = 5 * 1024 * 1024
DEFAULT_MAX_EXTRACTED_BYTES = 8 * 1024 * 1024
DEFAULT_MAX_EXTRACTED_FILES = 32
DEFAULT_ALLOWED_EXTENSIONS = frozenset({".sol", ".json", ".md", ".txt", ".toml"})
DEFAULT_DOWNLOAD_TIMEOUT_SECONDS = 15
_CHUNK_SIZE = 64 * 1024


@dataclass
class ResolvedExecutableEvidence:
    source_path: Path
    source_root: Path
    source_text: str
    manifest: dict[str, Any]
    bundle_mode: bool
    materialized_root: Path | None = None
    _tempdir: tempfile.TemporaryDirectory[str] | None = field(
        default=None, repr=False
    )

    def cleanup(self) -> None:
        if self._tempdir is not None:
            self._tempdir.cleanup()
            self._tempdir = None

    def __enter__(self) -> "ResolvedExecutableEvidence":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        del exc_type, exc, tb
        self.cleanup()


class EvidenceResolutionError(ValueError):
    pass


UrlOpen = Callable[..., Any]


class ExecutableEvidenceResolver:
    def __init__(
        self,
        *,
        ipfs_gateway: str | None = None,
        max_download_bytes: int = DEFAULT_MAX_DOWNLOAD_BYTES,
        max_extracted_bytes: int = DEFAULT_MAX_EXTRACTED_BYTES,
        max_extracted_files: int = DEFAULT_MAX_EXTRACTED_FILES,
        allowed_extensions: frozenset[str] = DEFAULT_ALLOWED_EXTENSIONS,
        download_timeout_seconds: int = DEFAULT_DOWNLOAD_TIMEOUT_SECONDS,
        urlopen: UrlOpen | None = None,
    ) -> None:
        self.ipfs_gateway = (
            ipfs_gateway
            or os.environ.get("PROOF_OF_AUDIT_IPFS_GATEWAY")
            or DEFAULT_IPFS_GATEWAY
        ).rstrip("/")
        self.max_download_bytes = max_download_bytes
        self.max_extracted_bytes = max_extracted_bytes
        self.max_extracted_files = max_extracted_files
        self.allowed_extensions = allowed_extensions
        self.download_timeout_seconds = download_timeout_seconds
        self._urlopen = urlopen or request.urlopen

    def resolve(self, context: EvidenceContext) -> ResolvedExecutableEvidence:
        parsed = parse.urlparse(context.proof_uri)
        if parsed.scheme in {"", "file"}:
            source_path = self._resolve_local_source_path(context.proof_uri)
            if source_path is None or not source_path.is_file():
                raise EvidenceResolutionError(
                    "Executable evidence must point to an existing local Solidity test file."
                )
            source_text = self._read_text(source_path)
            manifest = self._resolve_manifest(
                source_root=source_path.parent,
                source_path=source_path,
                request_manifest=context.evidence_manifest,
            )
            self._validate_hashes(source_path.parent, manifest)
            return ResolvedExecutableEvidence(
                source_path=source_path,
                source_root=source_path.parent,
                source_text=source_text,
                manifest=manifest,
                bundle_mode=False,
            )

        if parsed.scheme not in {"ipfs", "https", "http"}:
            raise EvidenceResolutionError(
                "Executable evidence supports local paths, file://, ipfs://, http://, and https:// URIs."
            )

        tempdir = tempfile.TemporaryDirectory(prefix="proof-of-audit-fetch-")
        materialized_root = Path(tempdir.name)
        try:
            downloaded_path = self._download_remote_uri(
                context.proof_uri,
                materialized_root / "downloaded",
            )
            if self._is_archive(downloaded_path):
                extracted_root = materialized_root / "extracted"
                extracted_root.mkdir(parents=True, exist_ok=True)
                self._extract_archive(downloaded_path, extracted_root)
                bundle_root = self._resolve_bundle_root(extracted_root)
                manifest = self._resolve_manifest(
                    source_root=bundle_root,
                    source_path=None,
                    request_manifest=context.evidence_manifest,
                )
                entrypoint = self._resolve_entrypoint(bundle_root, manifest)
                self._validate_hashes(bundle_root, manifest)
                return ResolvedExecutableEvidence(
                    source_path=entrypoint,
                    source_root=bundle_root,
                    source_text=self._read_text(entrypoint),
                    manifest=manifest,
                    bundle_mode=True,
                    materialized_root=materialized_root,
                    _tempdir=tempdir,
                )

            self._validate_file_path(downloaded_path)
            source_text = self._read_text(downloaded_path)
            manifest = self._resolve_manifest(
                source_root=downloaded_path.parent,
                source_path=downloaded_path,
                request_manifest=context.evidence_manifest,
            )
            self._validate_hashes(downloaded_path.parent, manifest)
            return ResolvedExecutableEvidence(
                source_path=downloaded_path,
                source_root=downloaded_path.parent,
                source_text=source_text,
                manifest=manifest,
                bundle_mode=False,
                materialized_root=materialized_root,
                _tempdir=tempdir,
            )
        except Exception:
            tempdir.cleanup()
            raise

    def _download_remote_uri(self, proof_uri: str, destination_stub: Path) -> Path:
        remote_url = self._translate_remote_uri(proof_uri)
        req = request.Request(
            remote_url,
            headers={"Accept": "application/octet-stream, application/zip, application/x-tar"},
            method="GET",
        )
        total = 0
        filename = self._suggest_filename(proof_uri)
        destination = destination_stub.with_name(filename)
        with self._urlopen(req, timeout=self.download_timeout_seconds) as response:
            with destination.open("wb") as handle:
                while True:
                    chunk = response.read(_CHUNK_SIZE)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > self.max_download_bytes:
                        raise EvidenceResolutionError(
                            "Executable evidence download exceeded the maximum allowed size."
                        )
                    handle.write(chunk)
        if total == 0:
            raise EvidenceResolutionError("Executable evidence download was empty.")
        return destination

    def _translate_remote_uri(self, proof_uri: str) -> str:
        parsed = parse.urlparse(proof_uri)
        if parsed.scheme == "ipfs":
            path = parsed.netloc + parsed.path
            return f"{self.ipfs_gateway}/{path.lstrip('/')}"
        return proof_uri

    def _suggest_filename(self, proof_uri: str) -> str:
        parsed = parse.urlparse(proof_uri)
        path_name = Path(parse.unquote(parsed.path)).name
        if path_name:
            return path_name
        if parsed.netloc:
            return parsed.netloc
        return "evidence.bin"

    def _resolve_local_source_path(self, proof_uri: str) -> Path | None:
        parsed = parse.urlparse(proof_uri)
        if parsed.scheme == "file":
            return Path(parse.unquote(parsed.path))
        if parsed.scheme:
            return None
        candidate = Path(proof_uri)
        if not candidate.is_absolute():
            return None
        return candidate

    def _resolve_manifest(
        self,
        *,
        source_root: Path,
        source_path: Path | None,
        request_manifest: dict[str, Any] | None,
    ) -> dict[str, Any]:
        manifest = dict(request_manifest or {})
        bundle_manifest_path = source_root / "manifest.json"
        if bundle_manifest_path.is_file():
            try:
                bundle_manifest = json.loads(bundle_manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise EvidenceResolutionError(
                    f"Executable evidence manifest.json is invalid: {exc}"
                ) from exc
            if not manifest:
                manifest = bundle_manifest

        if source_path is not None and manifest:
            entrypoint = manifest.get("entrypoint")
            if isinstance(entrypoint, str) and entrypoint and Path(entrypoint).name != source_path.name:
                raise EvidenceResolutionError(
                    "Executable evidence manifest entrypoint does not match the submitted file."
                )
        return manifest

    def _resolve_entrypoint(self, source_root: Path, manifest: dict[str, Any]) -> Path:
        entrypoint = manifest.get("entrypoint")
        if isinstance(entrypoint, str) and entrypoint:
            entry_path = source_root / PurePosixPath(entrypoint)
            if not entry_path.is_file():
                raise EvidenceResolutionError(
                    "Executable evidence bundle entrypoint was not found after extraction."
                )
            self._validate_file_path(entry_path)
            return entry_path

        sol_files = sorted(path for path in source_root.rglob("*.sol") if path.is_file())
        if len(sol_files) == 1:
            return sol_files[0]
        raise EvidenceResolutionError(
            "Executable evidence archives must include manifest.json with an entrypoint or contain exactly one Solidity test file."
        )

    def _resolve_bundle_root(self, extracted_root: Path) -> Path:
        manifest_path = extracted_root / "manifest.json"
        if manifest_path.is_file():
            return extracted_root

        top_level_dirs = sorted(
            path for path in extracted_root.iterdir() if path.is_dir()
        )
        top_level_files = [path for path in extracted_root.iterdir() if path.is_file()]
        if not top_level_files and len(top_level_dirs) == 1:
            return top_level_dirs[0]
        return extracted_root

    def _validate_hashes(self, source_root: Path, manifest: dict[str, Any]) -> None:
        expected_hashes = manifest.get("expected_file_hashes")
        if not isinstance(expected_hashes, dict):
            return
        for relative_path, expected_hash in expected_hashes.items():
            if not isinstance(relative_path, str) or not isinstance(expected_hash, str):
                raise EvidenceResolutionError(
                    "Executable evidence manifest expected_file_hashes entries must be string-to-string mappings."
                )
            file_path = source_root / PurePosixPath(relative_path)
            if not file_path.is_file():
                raise EvidenceResolutionError(
                    f"Executable evidence expected hash target is missing: {relative_path}"
                )
            actual_hash = sha256(file_path.read_bytes()).hexdigest()
            if actual_hash != expected_hash.lower():
                raise EvidenceResolutionError(
                    f"Executable evidence hash mismatch for {relative_path}."
                )

    def _is_archive(self, path: Path) -> bool:
        return zipfile.is_zipfile(path) or tarfile.is_tarfile(path)

    def _extract_archive(self, archive_path: Path, destination: Path) -> None:
        if zipfile.is_zipfile(archive_path):
            self._extract_zip(archive_path, destination)
            return
        if tarfile.is_tarfile(archive_path):
            self._extract_tar(archive_path, destination)
            return
        raise EvidenceResolutionError("Executable evidence archive type is not supported.")

    def _extract_zip(self, archive_path: Path, destination: Path) -> None:
        extracted_files = 0
        extracted_bytes = 0
        with zipfile.ZipFile(archive_path) as archive:
            for info in archive.infolist():
                target = self._safe_target_path(destination, info.filename)
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                mode = info.external_attr >> 16
                if stat.S_ISLNK(mode):
                    raise EvidenceResolutionError(
                        "Executable evidence archives may not contain symlinks."
                    )
                extracted_files += 1
                extracted_bytes += int(info.file_size)
                self._check_extraction_limits(extracted_files, extracted_bytes)
                self._validate_file_path(target)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, target.open("wb") as handle:
                    shutil.copyfileobj(source, handle)

    def _extract_tar(self, archive_path: Path, destination: Path) -> None:
        extracted_files = 0
        extracted_bytes = 0
        with tarfile.open(archive_path) as archive:
            for member in archive.getmembers():
                target = self._safe_target_path(destination, member.name)
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                if member.issym() or member.islnk():
                    raise EvidenceResolutionError(
                        "Executable evidence archives may not contain symlinks."
                    )
                if not member.isfile():
                    raise EvidenceResolutionError(
                        "Executable evidence archives may only contain regular files and directories."
                    )
                extracted_files += 1
                extracted_bytes += int(member.size)
                self._check_extraction_limits(extracted_files, extracted_bytes)
                self._validate_file_path(target)
                target.parent.mkdir(parents=True, exist_ok=True)
                extracted = archive.extractfile(member)
                if extracted is None:
                    raise EvidenceResolutionError(
                        "Executable evidence archive entry could not be extracted."
                    )
                with extracted, target.open("wb") as handle:
                    shutil.copyfileobj(extracted, handle)

    def _safe_target_path(self, destination: Path, member_name: str) -> Path:
        candidate = PurePosixPath(member_name)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise EvidenceResolutionError(
                "Executable evidence archives may not contain absolute or parent-traversing paths."
            )
        return destination / Path(*candidate.parts)

    def _check_extraction_limits(self, file_count: int, extracted_bytes: int) -> None:
        if file_count > self.max_extracted_files:
            raise EvidenceResolutionError(
                "Executable evidence archive exceeded the maximum extracted file count."
            )
        if extracted_bytes > self.max_extracted_bytes:
            raise EvidenceResolutionError(
                "Executable evidence archive exceeded the maximum extracted size."
            )

    def _validate_file_path(self, path: Path) -> None:
        if path.name.startswith("."):
            raise EvidenceResolutionError(
                "Executable evidence may not contain hidden files."
            )
        extension = path.suffix.lower()
        if extension not in self.allowed_extensions:
            raise EvidenceResolutionError(
                f"Executable evidence file type is not allowed: {path.name}"
            )

    def _read_text(self, path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:
            raise EvidenceResolutionError(
                f"Executable evidence could not be read from disk: {exc}"
            ) from exc
