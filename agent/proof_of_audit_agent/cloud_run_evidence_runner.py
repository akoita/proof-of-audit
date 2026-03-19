from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Callable
from urllib import parse
import zipfile


DEFAULT_WORKDIR = "/workspace"
ALLOWED_ENV_KEYS = {
    "HOME",
    "USER",
    "LANG",
    "LC_ALL",
    "FOUNDRY_DISABLE_NIGHTLY_WARNING",
    "FOUNDRY_DISABLE_TELEMETRY",
}
StorageClientFactory = Callable[[], object]


def default_storage_client_factory() -> object:
    try:
        from google.cloud import storage
    except ImportError as exc:  # pragma: no cover - depends on optional runtime dep
        raise EvidenceExecutionRequestError(
            "google-cloud-storage is required for GCS-backed Cloud Run evidence execution."
        ) from exc
    return storage.Client()


def _build_preexec_fn(memory_limit_bytes: int) -> Callable[[], None] | None:
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


class EvidenceExecutionRequestError(ValueError):
    pass


def execute_payload(
    payload: object,
    *,
    storage_client_factory: StorageClientFactory | None = None,
) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise EvidenceExecutionRequestError("Payload must be a JSON object.")
    command = payload.get("command")
    if not isinstance(command, list) or not command or not all(
        isinstance(item, str) and item for item in command
    ):
        raise EvidenceExecutionRequestError("command must be a non-empty string list.")
    if command[0] != "forge":
        raise EvidenceExecutionRequestError("Only forge execution is supported.")
    archive_format = payload.get("archive_format")
    if archive_format != "zip":
        raise EvidenceExecutionRequestError("archive_format must be zip.")
    timeout_seconds = payload.get("timeout_seconds")
    if not isinstance(timeout_seconds, int) or timeout_seconds <= 0:
        raise EvidenceExecutionRequestError("timeout_seconds must be a positive integer.")
    memory_limit_bytes = payload.get("memory_limit_bytes")
    if not isinstance(memory_limit_bytes, int) or memory_limit_bytes <= 0:
        raise EvidenceExecutionRequestError(
            "memory_limit_bytes must be a positive integer."
        )
    working_directory = payload.get("working_directory", DEFAULT_WORKDIR)
    if not isinstance(working_directory, str) or not working_directory.startswith("/"):
        raise EvidenceExecutionRequestError(
            "working_directory must be an absolute virtual path."
        )
    env = payload.get("env") or {}
    if not isinstance(env, dict):
        raise EvidenceExecutionRequestError("env must be an object.")
    filtered_env = {
        key: value
        for key, value in env.items()
        if key in ALLOWED_ENV_KEYS and isinstance(value, str)
    }
    archive_bytes = _resolve_archive_bytes(
        payload,
        storage_client_factory=storage_client_factory,
    )

    with tempfile.TemporaryDirectory(prefix="proof-of-audit-cloud-run-") as tmpdir:
        root = Path(tmpdir) / "workspace"
        root.mkdir(parents=True, exist_ok=True)
        archive_path = Path(tmpdir) / "evidence.zip"
        archive_path.write_bytes(archive_bytes)
        with zipfile.ZipFile(archive_path) as archive:
            _extract_archive_safely(archive, root)

        runtime_home = Path(tmpdir) / "home"
        runtime_home.mkdir(parents=True, exist_ok=True)
        runtime_env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": filtered_env.get("HOME", str(runtime_home)),
            "USER": filtered_env.get("USER", "proof-of-audit"),
            "LANG": filtered_env.get("LANG", "C.UTF-8"),
            "LC_ALL": filtered_env.get("LC_ALL", "C.UTF-8"),
            "FOUNDRY_DISABLE_NIGHTLY_WARNING": filtered_env.get(
                "FOUNDRY_DISABLE_NIGHTLY_WARNING", "1"
            ),
            "FOUNDRY_DISABLE_TELEMETRY": filtered_env.get(
                "FOUNDRY_DISABLE_TELEMETRY", "1"
            ),
        }
        translated_command = [
            _translate_remote_path(item, working_directory, root)
            for item in command
        ]
        result = subprocess.run(
            translated_command,
            cwd=root,
            env=runtime_env,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            preexec_fn=_build_preexec_fn(memory_limit_bytes),
            check=False,
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }


def _resolve_archive_bytes(
    payload: dict[str, object],
    *,
    storage_client_factory: StorageClientFactory | None = None,
) -> bytes:
    archive_gcs_uri = payload.get("archive_gcs_uri")
    if isinstance(archive_gcs_uri, str) and archive_gcs_uri:
        return _download_archive_from_gcs(
            archive_gcs_uri,
            generation=payload.get("archive_generation"),
            storage_client_factory=storage_client_factory,
        )
    archive_base64 = payload.get("archive_base64")
    if isinstance(archive_base64, str) and archive_base64:
        return base64.b64decode(archive_base64.encode("ascii"))
    raise EvidenceExecutionRequestError(
        "archive_base64 or archive_gcs_uri is required."
    )


def _download_archive_from_gcs(
    archive_gcs_uri: str,
    *,
    generation: object = None,
    storage_client_factory: StorageClientFactory | None = None,
) -> bytes:
    bucket_name, object_name = _parse_gcs_uri(archive_gcs_uri)
    client = (
        storage_client_factory() if storage_client_factory is not None else default_storage_client_factory()
    )
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(object_name)
    if generation is not None:
        blob.generation = int(generation)
    data = blob.download_as_bytes()
    if not isinstance(data, bytes):
        raise EvidenceExecutionRequestError("GCS archive download did not return bytes.")
    return data


def _parse_gcs_uri(uri: str) -> tuple[str, str]:
    parsed = parse.urlparse(uri)
    if parsed.scheme != "gs" or not parsed.netloc or not parsed.path:
        raise EvidenceExecutionRequestError("archive_gcs_uri must be a valid gs:// URI.")
    object_name = parsed.path.lstrip("/")
    if not object_name:
        raise EvidenceExecutionRequestError("archive_gcs_uri must include an object path.")
    return parsed.netloc, object_name


def _translate_remote_path(argument: str, working_directory: str, root: Path) -> str:
    if not argument.startswith(f"{working_directory}/") and argument != working_directory:
        return argument
    relative = argument[len(working_directory) :].lstrip("/")
    if not relative:
        return str(root)
    return str(root / relative)


def _extract_archive_safely(archive: zipfile.ZipFile, root: Path) -> None:
    root = root.resolve()
    for member in archive.infolist():
        target = (root / member.filename).resolve()
        if root not in target.parents and target != root:
            raise EvidenceExecutionRequestError(
                "archive contains an entry outside the workspace root"
            )
        archive.extract(member, root)
