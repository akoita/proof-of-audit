from __future__ import annotations

import base64
import io
import json
from pathlib import Path
from uuid import uuid4
from typing import Callable
from urllib import error, parse, request
import zipfile

from proof_of_audit_agent.backends.base import (
    EvidenceExecutionBackend,
    EvidenceExecutionResult,
)


Urlopen = Callable[..., object]
StorageClientFactory = Callable[[], object]

DEFAULT_REMOTE_WORKDIR = "/workspace"
DEFAULT_METADATA_IDENTITY_URL = (
    "http://metadata.google.internal/computeMetadata/v1/instance/"
    "service-accounts/default/identity"
)
DEFAULT_STAGING_PREFIX = "proof-of-audit/evidence"


def default_storage_client_factory() -> object:
    try:
        from google.cloud import storage
    except ImportError as exc:  # pragma: no cover - depends on installed extras
        raise OSError(
            "google-cloud-storage is required for GCS-staged Cloud Run evidence execution."
        ) from exc
    return storage.Client()


class GCPCloudRunBackend(EvidenceExecutionBackend):
    def __init__(
        self,
        *,
        service_url: str,
        audience: str | None = None,
        bearer_token: str | None = None,
        allow_unauthenticated: bool = False,
        staging_bucket: str | None = None,
        staging_prefix: str = DEFAULT_STAGING_PREFIX,
        metadata_identity_url: str = DEFAULT_METADATA_IDENTITY_URL,
        urlopen: Urlopen | None = None,
        metadata_urlopen: Urlopen | None = None,
        storage_client_factory: StorageClientFactory | None = None,
    ) -> None:
        self.service_url = service_url.rstrip("/")
        self.audience = audience
        self.bearer_token = bearer_token
        self.allow_unauthenticated = allow_unauthenticated
        self.staging_bucket = (staging_bucket or "").strip() or None
        self.staging_prefix = staging_prefix.strip().strip("/")
        self.metadata_identity_url = metadata_identity_url
        self._urlopen = urlopen or request.urlopen
        self._metadata_urlopen = metadata_urlopen or self._urlopen
        self._storage_client_factory = (
            storage_client_factory or default_storage_client_factory
        )

    @property
    def backend_name(self) -> str:
        return "gcp_cloud_run"

    @property
    def isolation_level(self) -> str:
        return "cloud"

    def is_available(self) -> bool:
        if not self.service_url:
            return False
        return bool(
            self.allow_unauthenticated or self.bearer_token or self.audience
        )

    def execute(
        self,
        *,
        command: list[str],
        cwd: Path,
        env: dict[str, str],
        timeout_seconds: int,
        memory_limit_bytes: int,
    ) -> EvidenceExecutionResult:
        if not command:
            raise OSError("Executable evidence runner produced an empty command.")
        archive_bytes = self._encode_archive(cwd.resolve())
        payload = {
            "command": self._translate_command(command, cwd.resolve()),
            "env": self._remote_env(env),
            "timeout_seconds": timeout_seconds,
            "memory_limit_bytes": memory_limit_bytes,
            "working_directory": DEFAULT_REMOTE_WORKDIR,
            "archive_format": "zip",
        }
        payload.update(self._archive_payload(archive_bytes))
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "proof-of-audit-cloud-run-backend/1",
        }
        auth_header = self._authorization_header(timeout_seconds)
        if auth_header is not None:
            headers["Authorization"] = auth_header
        req = request.Request(
            self.service_url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with self._urlopen(req, timeout=timeout_seconds + 5) as response:
                raw_body = response.read().decode("utf-8")
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise OSError(
                f"Cloud Run evidence backend request failed with status {exc.code}: {body}"
            ) from exc
        except (error.URLError, TimeoutError, OSError) as exc:
            raise OSError(f"Cloud Run evidence backend request failed: {exc}") from exc

        try:
            body = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise OSError("Cloud Run evidence backend returned invalid JSON.") from exc
        if not isinstance(body, dict):
            raise OSError("Cloud Run evidence backend returned an invalid response.")
        returncode = body.get("returncode")
        stdout = body.get("stdout", "")
        stderr = body.get("stderr", "")
        if not isinstance(returncode, int):
            raise OSError("Cloud Run evidence backend did not return a valid returncode.")
        if not isinstance(stdout, str) or not isinstance(stderr, str):
            raise OSError("Cloud Run evidence backend returned invalid process output.")
        return EvidenceExecutionResult(
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
            backend=self.backend_name,
            isolation_level=self.isolation_level,
        )

    def _authorization_header(self, timeout_seconds: int) -> str | None:
        if self.bearer_token:
            return f"Bearer {self.bearer_token}"
        if self.allow_unauthenticated:
            return None
        if not self.audience:
            raise OSError(
                "Cloud Run backend requires a bearer token, metadata audience, "
                "or explicit unauthenticated mode."
            )
        query = parse.urlencode({"audience": self.audience, "format": "full"})
        token_req = request.Request(
            f"{self.metadata_identity_url}?{query}",
            headers={"Metadata-Flavor": "Google"},
            method="GET",
        )
        try:
            with self._metadata_urlopen(
                token_req,
                timeout=min(timeout_seconds, 10),
            ) as resp:
                token = resp.read().decode("utf-8").strip()
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise OSError(
                f"Cloud Run backend could not fetch an identity token: {exc.code} {body}"
            ) from exc
        except (error.URLError, TimeoutError, OSError) as exc:
            raise OSError(
                f"Cloud Run backend could not fetch an identity token: {exc}"
            ) from exc
        if not token:
            raise OSError("Cloud Run backend received an empty identity token.")
        return f"Bearer {token}"

    def _encode_archive(self, cwd: Path) -> bytes:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(cwd.rglob("*")):
                if not path.is_file():
                    continue
                archive.write(path, arcname=path.relative_to(cwd))
        return buffer.getvalue()

    def _archive_payload(self, archive_bytes: bytes) -> dict[str, object]:
        if self.staging_bucket is not None:
            uri, generation = self._stage_archive(archive_bytes)
            payload: dict[str, object] = {"archive_gcs_uri": uri}
            if generation is not None:
                payload["archive_generation"] = generation
            return payload
        return {
            "archive_base64": base64.b64encode(archive_bytes).decode("ascii"),
        }

    def _stage_archive(self, archive_bytes: bytes) -> tuple[str, int | None]:
        client = self._storage_client_factory()
        bucket = client.bucket(self.staging_bucket)
        object_name = f"{self.staging_prefix}/{uuid4().hex}.zip"
        blob = bucket.blob(object_name)
        blob.upload_from_string(archive_bytes, content_type="application/zip")
        generation = getattr(blob, "generation", None)
        return (
            f"gs://{self.staging_bucket}/{object_name}",
            int(generation) if generation is not None else None,
        )

    def _remote_env(self, env: dict[str, str]) -> dict[str, str]:
        return {
            "HOME": env.get("HOME", "/tmp/proof-of-audit-home"),
            "USER": env.get("USER", "proof-of-audit"),
            "LANG": env.get("LANG", "C.UTF-8"),
            "LC_ALL": env.get("LC_ALL", "C.UTF-8"),
            "FOUNDRY_DISABLE_NIGHTLY_WARNING": env.get(
                "FOUNDRY_DISABLE_NIGHTLY_WARNING", "1"
            ),
            "FOUNDRY_DISABLE_TELEMETRY": env.get("FOUNDRY_DISABLE_TELEMETRY", "1"),
        }

    def _translate_command(self, command: list[str], cwd: Path) -> list[str]:
        translated = ["forge"]
        translated.extend(
            self._translate_path_argument(argument, cwd)
            for argument in command[1:]
        )
        return translated

    def _translate_path_argument(self, argument: str, cwd: Path) -> str:
        path = Path(argument)
        if not path.is_absolute():
            return argument
        try:
            relative = path.resolve().relative_to(cwd)
        except ValueError:
            return argument
        return str(Path(DEFAULT_REMOTE_WORKDIR) / relative)
