from __future__ import annotations

import base64
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Callable
import zipfile


DEFAULT_PORT = 8080
DEFAULT_WORKDIR = "/workspace"
ALLOWED_ENV_KEYS = {
    "HOME",
    "USER",
    "LANG",
    "LC_ALL",
    "FOUNDRY_DISABLE_NIGHTLY_WARNING",
    "FOUNDRY_DISABLE_TELEMETRY",
}


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


class RunnerHandler(BaseHTTPRequestHandler):
    server_version = "ProofOfAuditCloudRunEvidenceRunner/1"

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/execute":
            self._write_json(
                HTTPStatus.NOT_FOUND,
                {"error": "not_found"},
            )
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(length)
            payload = json.loads(raw_body.decode("utf-8"))
            result = execute_payload(payload)
        except EvidenceExecutionRequestError as exc:
            self._write_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_request", "detail": str(exc)},
            )
            return
        except subprocess.TimeoutExpired as exc:
            self._write_json(
                HTTPStatus.OK,
                {
                    "returncode": 124,
                    "stdout": exc.stdout or "",
                    "stderr": exc.stderr or "",
                },
            )
            return
        except json.JSONDecodeError:
            self._write_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_json"},
            )
            return
        except Exception as exc:  # pragma: no cover - defensive cloud service path
            self._write_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": "runner_error", "detail": str(exc)},
            )
            return
        self._write_json(HTTPStatus.OK, result)

    def log_message(self, format: str, *args: object) -> None:
        del format, args

    def _write_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def execute_payload(payload: object) -> dict[str, object]:
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
    archive_base64 = payload.get("archive_base64")
    if not isinstance(archive_base64, str) or not archive_base64:
        raise EvidenceExecutionRequestError("archive_base64 is required.")
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
    archive_bytes = base64.b64decode(archive_base64.encode("ascii"))

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


def main() -> None:
    port = int(os.environ.get("PORT", str(DEFAULT_PORT)))
    server = ThreadingHTTPServer(("0.0.0.0", port), RunnerHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
