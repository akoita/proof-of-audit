from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any, Mapping
from urllib import parse, request
from uuid import uuid4


UPLOAD_SUFFIXES = {".sol", ".zip"}
DEFAULT_SOURCE_BUNDLE_STORAGE_KIND = "local"
DEFAULT_SOURCE_BUNDLE_GCS_PREFIX = "source-bundles"
DEFAULT_IPFS_UPLOAD_TIMEOUT_SECONDS = 30


class SourceBundleStorageError(ValueError):
    pass


@dataclass(frozen=True)
class StoredSourceBundle:
    original_filename: str
    source_bundle_uri: str
    storage_backend: str
    source_bundle_label: str | None = None
    entry_contract: str | None = None


class SourceBundleStorage:
    storage_backend = DEFAULT_SOURCE_BUNDLE_STORAGE_KIND

    def store(self, *, original_filename: str, content: bytes) -> StoredSourceBundle:
        raise NotImplementedError


class LocalSourceBundleStorage(SourceBundleStorage):
    storage_backend = "local"

    def __init__(self, workspace_root: Path) -> None:
        self.uploads_dir = workspace_root / "uploads"

    def store(self, *, original_filename: str, content: bytes) -> StoredSourceBundle:
        stem = Path(original_filename).stem
        suffix = Path(original_filename).suffix.lower()
        normalized_stem = _normalize_stem(stem)
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        destination = self.uploads_dir / f"{normalized_stem}-{uuid4().hex}{suffix}"
        destination.write_bytes(content)
        return StoredSourceBundle(
            original_filename=original_filename,
            source_bundle_uri=str(destination),
            storage_backend=self.storage_backend,
            source_bundle_label=stem or None,
            entry_contract=stem if suffix == ".sol" and stem else None,
        )


class GcsSourceBundleStorage(SourceBundleStorage):
    storage_backend = "gcs"

    def __init__(
        self,
        *,
        bucket_name: str,
        prefix: str = DEFAULT_SOURCE_BUNDLE_GCS_PREFIX,
    ) -> None:
        self.bucket_name = bucket_name
        self.prefix = prefix.strip("/")

    def store(self, *, original_filename: str, content: bytes) -> StoredSourceBundle:
        storage = _require_gcs_storage()
        stem = Path(original_filename).stem
        suffix = Path(original_filename).suffix.lower()
        object_name = _build_object_name(self.prefix, stem, suffix)
        try:
            client = storage.Client()
            bucket = client.bucket(self.bucket_name)
            blob = bucket.blob(object_name)
            blob.upload_from_string(content, content_type=_content_type_for_suffix(suffix))
        except Exception as exc:
            raise SourceBundleStorageError(f"GCS upload failed: {exc}") from exc
        return StoredSourceBundle(
            original_filename=original_filename,
            source_bundle_uri=f"gs://{self.bucket_name}/{object_name}",
            storage_backend=self.storage_backend,
            source_bundle_label=stem or None,
            entry_contract=stem if suffix == ".sol" and stem else None,
        )


class IpfsSourceBundleStorage(SourceBundleStorage):
    storage_backend = "ipfs"

    def __init__(
        self,
        *,
        api_url: str,
        auth_header: str | None = None,
        timeout_seconds: int = DEFAULT_IPFS_UPLOAD_TIMEOUT_SECONDS,
    ) -> None:
        self.api_url = _normalize_ipfs_api_url(api_url)
        self.auth_header = auth_header
        self.timeout_seconds = timeout_seconds

    def store(self, *, original_filename: str, content: bytes) -> StoredSourceBundle:
        stem = Path(original_filename).stem
        suffix = Path(original_filename).suffix.lower()
        boundary = f"proof-of-audit-{uuid4().hex}"
        body = _build_ipfs_multipart_body(
            boundary=boundary,
            filename=original_filename,
            content=content,
            content_type=_content_type_for_suffix(suffix),
        )
        headers = {
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "application/json",
        }
        if self.auth_header:
            key, value = _split_header(self.auth_header)
            headers[key] = value
        req = request.Request(
            self.api_url,
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                payload = response.read().decode("utf-8")
        except Exception as exc:
            raise SourceBundleStorageError(f"IPFS upload failed: {exc}") from exc
        cid = _extract_ipfs_cid(payload)
        return StoredSourceBundle(
            original_filename=original_filename,
            source_bundle_uri=f"ipfs://{cid}/{Path(original_filename).name}",
            storage_backend=self.storage_backend,
            source_bundle_label=stem or None,
            entry_contract=stem if suffix == ".sol" and stem else None,
        )


def build_source_bundle_storage(
    *,
    workspace_root: Path,
    env: Mapping[str, str],
) -> SourceBundleStorage:
    kind = (
        env.get("PROOF_OF_AUDIT_SOURCE_BUNDLE_STORAGE_KIND")
        or DEFAULT_SOURCE_BUNDLE_STORAGE_KIND
    ).strip().lower()
    if kind == "local":
        return LocalSourceBundleStorage(workspace_root)
    if kind == "gcs":
        bucket_name = str(env.get("PROOF_OF_AUDIT_SOURCE_BUNDLE_GCS_BUCKET") or "").strip()
        if not bucket_name:
            raise SourceBundleStorageError(
                "GCS source bundle storage requires PROOF_OF_AUDIT_SOURCE_BUNDLE_GCS_BUCKET."
            )
        return GcsSourceBundleStorage(
            bucket_name=bucket_name,
            prefix=str(
                env.get("PROOF_OF_AUDIT_SOURCE_BUNDLE_GCS_PREFIX")
                or DEFAULT_SOURCE_BUNDLE_GCS_PREFIX
            ),
        )
    if kind == "ipfs":
        api_url = str(env.get("PROOF_OF_AUDIT_SOURCE_BUNDLE_IPFS_API_URL") or "").strip()
        if not api_url:
            raise SourceBundleStorageError(
                "IPFS source bundle storage requires PROOF_OF_AUDIT_SOURCE_BUNDLE_IPFS_API_URL."
            )
        return IpfsSourceBundleStorage(
            api_url=api_url,
            auth_header=str(
                env.get("PROOF_OF_AUDIT_SOURCE_BUNDLE_IPFS_AUTH_HEADER") or ""
            ).strip()
            or None,
        )
    raise SourceBundleStorageError(f"Unsupported source bundle storage kind: {kind}")


def validate_upload_filename(filename: str) -> str:
    original_name = Path(filename).name
    suffix = Path(original_name).suffix.lower()
    if not original_name or suffix not in UPLOAD_SUFFIXES:
        raise SourceBundleStorageError(
            "Only .zip and .sol files are supported for source bundle uploads."
        )
    return original_name


def _normalize_stem(stem: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("-._") or "source-bundle"


def _build_object_name(prefix: str, stem: str, suffix: str) -> str:
    normalized_stem = _normalize_stem(stem)
    filename = f"{normalized_stem}-{uuid4().hex}{suffix}"
    cleaned_prefix = prefix.strip("/")
    return f"{cleaned_prefix}/{filename}" if cleaned_prefix else filename


def _content_type_for_suffix(suffix: str) -> str:
    if suffix == ".zip":
        return "application/zip"
    return "text/plain; charset=utf-8"


def _normalize_ipfs_api_url(url: str) -> str:
    parsed = parse.urlparse(url)
    base_path = parsed.path.rstrip("/")
    if not base_path.endswith("/api/v0/add"):
        base_path = f"{base_path}/api/v0/add"
    query_pairs = parse.parse_qsl(parsed.query, keep_blank_values=True)
    query = dict(query_pairs)
    query.setdefault("pin", "true")
    query.setdefault("wrap-with-directory", "true")
    return parse.urlunparse(
        parsed._replace(
            path=base_path,
            query=parse.urlencode(query),
        )
    )


def _build_ipfs_multipart_body(
    *,
    boundary: str,
    filename: str,
    content: bytes,
    content_type: str,
) -> bytes:
    parts = [
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode("utf-8"),
        content,
        b"\r\n",
        (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="wrap-with-directory"\r\n\r\n'
            "true\r\n"
        ).encode("utf-8"),
        f"--{boundary}--\r\n".encode("utf-8"),
    ]
    return b"".join(parts)


def _split_header(raw_header: str) -> tuple[str, str]:
    name, separator, value = raw_header.partition(":")
    if not separator or not name.strip() or not value.strip():
        raise SourceBundleStorageError(
            "PROOF_OF_AUDIT_SOURCE_BUNDLE_IPFS_AUTH_HEADER must look like 'Authorization: Bearer <token>'."
        )
    return name.strip(), value.strip()


def _extract_ipfs_cid(payload: str) -> str:
    entries = []
    for line in payload.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            entries.append(json.loads(stripped))
        except json.JSONDecodeError as exc:
            raise SourceBundleStorageError(
                f"IPFS upload returned invalid JSON: {exc}"
            ) from exc
    if not entries:
        raise SourceBundleStorageError("IPFS upload returned no JSON payload.")
    last = entries[-1]
    cid = last.get("Hash") if isinstance(last, dict) else None
    if not isinstance(cid, str) or not cid:
        raise SourceBundleStorageError("IPFS upload response did not include a CID hash.")
    return cid


def _require_gcs_storage() -> Any:
    try:
        from google.cloud import storage
    except ImportError as exc:
        raise SourceBundleStorageError(
            "google-cloud-storage is required for GCS source bundle storage."
        ) from exc
    return storage
