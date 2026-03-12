from __future__ import annotations

import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from proof_of_audit_api.service import AuditService


DATA_ROOT = Path(__file__).resolve().parents[1] / "data"
SERVICE = AuditService(DATA_ROOT)


class AuditRequestHandler(BaseHTTPRequestHandler):
    server_version = "ProofOfAuditHTTP/0.1"

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(HTTPStatus.NO_CONTENT.value)
        self._send_default_headers("application/json", "0")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        segments = self._segments(path)
        if segments == ["health"]:
            self._send_json({"status": "ok"})
            return
        if segments == ["audits"]:
            self._send_json({"items": SERVICE.list_audits()})
            return
        if len(segments) == 2 and segments[0] == "audits":
            record = SERVICE.get_audit(segments[1])
            if record is None:
                self._send_json(
                    {"error": "audit_not_found"}, status=HTTPStatus.NOT_FOUND
                )
                return
            self._send_json(record)
            return

        self._send_json({"error": "not_found"}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        segments = self._segments(path)
        body = self._json_body()

        try:
            if segments == ["audits"]:
                contract_address = body["contract_address"]
                submitted_by = body.get("submitted_by", "anonymous")
                record = SERVICE.create_audit(contract_address, submitted_by)
                self._send_json(record, status=HTTPStatus.CREATED)
                return

            if len(segments) == 3 and segments[0] == "audits" and segments[2] == "publish":
                record = SERVICE.publish_audit(
                    segments[1],
                    stake_wei=int(body.get("stake_wei", 10_000_000_000_000_000)),
                    agent_identity=body.get("agent_identity", "auditor-agent-v1"),
                )
                self._send_json(record)
                return

            if len(segments) == 3 and segments[0] == "audits" and segments[2] == "challenge":
                record = SERVICE.challenge_audit(
                    segments[1],
                    proof_uri=body["proof_uri"],
                    challenger=body.get("challenger", "anonymous-challenger"),
                )
                self._send_json(record)
                return
        except KeyError as exc:
            self._send_json(
                {"error": "missing_field", "field": str(exc)},
                status=HTTPStatus.BAD_REQUEST,
            )
            return
        except ValueError as exc:
            self._send_json(
                {"error": "invalid_payload", "message": str(exc)},
                status=HTTPStatus.BAD_REQUEST,
            )
            return

        self._send_json({"error": "not_found"}, status=HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args: object) -> None:
        return

    def _json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def _send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status.value)
        self._send_default_headers("application/json", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_default_headers(self, content_type: str, content_length: str) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", content_length)

    @staticmethod
    def _segments(path: str) -> list[str]:
        return [segment for segment in path.split("/") if segment]


def main() -> None:
    host = os.environ.get("PROOF_OF_AUDIT_HOST", "127.0.0.1")
    port = int(os.environ.get("PROOF_OF_AUDIT_PORT", "8080"))
    server = ThreadingHTTPServer((host, port), AuditRequestHandler)
    print(f"Proof-of-Audit API listening on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
