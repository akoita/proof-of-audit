from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any
from urllib.parse import urljoin

import httpx


_TERMINAL_RUN_STATUSES = {"completed", "failed", "cancelled"}


@dataclass(frozen=True)
class HostedRunResult:
    run_id: str
    status: str
    status_url: str | None
    report_url: str | None
    logs_url: str | None
    report_payload: dict[str, Any]
    logs_payload: dict[str, Any] | None = None


class AgentForgeServiceClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_token: str | None = None,
        request_timeout_seconds: float = 30.0,
        poll_interval_seconds: float = 0.25,
        poll_timeout_seconds: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token
        self.request_timeout_seconds = request_timeout_seconds
        self.poll_interval_seconds = poll_interval_seconds
        self.poll_timeout_seconds = poll_timeout_seconds

    def run(
        self,
        *,
        payload: dict[str, Any],
    ) -> HostedRunResult:
        headers = {"accept": "application/json"}
        if self.api_token:
            headers["authorization"] = f"Bearer {self.api_token}"
            headers["x-agent-forge-api-key"] = self.api_token
        with httpx.Client(timeout=self.request_timeout_seconds, headers=headers) as client:
            created = self._request(client, "POST", "/v1/runs", json=payload)
            run_id = str(created.get("run_id") or "").strip()
            if not run_id:
                raise ValueError("hosted agent-forge response did not include run_id")
            status_payload = self._wait_for_terminal_status(
                client,
                run_id=run_id,
                status_url=created.get("status_url"),
            )
            status = str(status_payload.get("status") or "").strip()
            if status != "completed":
                error = status_payload.get("error")
                if isinstance(error, dict):
                    message = str(error.get("message") or f"hosted agent-forge run {status}")
                else:
                    message = f"hosted agent-forge run {status}"
                raise ValueError(message)
            report_payload = self._request(
                client,
                "GET",
                status_payload.get("report_url") or f"/v1/runs/{run_id}/report",
            )
            logs_payload: dict[str, Any] | None
            try:
                logs_payload = self._request(
                    client,
                    "GET",
                    status_payload.get("logs_url") or f"/v1/runs/{run_id}/logs",
                )
            except ValueError:
                logs_payload = None
            return HostedRunResult(
                run_id=run_id,
                status=status,
                status_url=self._absolute_url(status_payload.get("status_url")),
                report_url=self._absolute_url(status_payload.get("report_url")),
                logs_url=self._absolute_url(status_payload.get("logs_url")),
                report_payload=report_payload,
                logs_payload=logs_payload,
            )

    def _wait_for_terminal_status(
        self,
        client: httpx.Client,
        *,
        run_id: str,
        status_url: object,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + self.poll_timeout_seconds
        current_url = status_url or f"/v1/runs/{run_id}"
        while True:
            payload = self._request(client, "GET", current_url)
            status = str(payload.get("status") or "").strip()
            if status in _TERMINAL_RUN_STATUSES:
                return payload
            if time.monotonic() >= deadline:
                raise ValueError(
                    f"timed out waiting for hosted agent-forge run {run_id} to complete"
                )
            time.sleep(self.poll_interval_seconds)

    def _request(
        self,
        client: httpx.Client,
        method: str,
        path_or_url: object,
        *,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = self._absolute_url(path_or_url)
        response = client.request(method, url, json=json)
        if response.status_code >= 400:
            raise ValueError(self._error_message(response))
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError(f"hosted agent-forge returned non-object JSON for {url}")
        return payload

    def _absolute_url(self, path_or_url: object) -> str:
        candidate = str(path_or_url or "").strip()
        if not candidate:
            return self.base_url
        if candidate.startswith("http://") or candidate.startswith("https://"):
            return candidate
        return urljoin(f"{self.base_url}/", candidate.lstrip("/"))

    def _error_message(self, response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            return response.text.strip() or f"hosted agent-forge request failed with {response.status_code}"
        if isinstance(payload, dict):
            detail = payload.get("detail")
            if isinstance(detail, dict):
                error = detail.get("error")
                if isinstance(error, dict):
                    message = str(error.get("message") or "").strip()
                    if message:
                        return message
            error = payload.get("error")
            if isinstance(error, dict):
                message = str(error.get("message") or "").strip()
                if message:
                    return message
            message = str(payload.get("message") or "").strip()
            if message:
                return message
        return response.text.strip() or f"hosted agent-forge request failed with {response.status_code}"
