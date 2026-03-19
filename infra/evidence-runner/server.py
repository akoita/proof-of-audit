from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
import subprocess
import sys

sys.path.insert(0, "/app/agent")

from proof_of_audit_agent.cloud_run_evidence_runner import (  # noqa: E402
    EvidenceExecutionRequestError,
    execute_payload,
)


DEFAULT_PORT = 8080


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
def main() -> None:
    port = int(os.environ.get("PORT", str(DEFAULT_PORT)))
    server = ThreadingHTTPServer(("0.0.0.0", port), RunnerHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
