from __future__ import annotations

from pathlib import Path
import tempfile

import httpx

from proof_of_audit_agent.request_participation import (
    AuditRequestMarketplaceClient,
    AuditRequestParticipationLoop,
    JsonlDecisionStore,
    ParticipationPolicy,
)


class FakeHttpClient:
    def __init__(
        self,
        responses: list[dict[str, object]],
        requests: list[dict[str, object]],
        **_: object,
    ) -> None:
        self._responses = responses
        self.requests = requests

    def __enter__(self) -> "FakeHttpClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        del exc_type, exc, tb
        return False

    def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, object] | None = None,
        json: dict[str, object] | None = None,
    ) -> httpx.Response:
        self.requests.append(
            {
                "method": method,
                "url": url,
                "params": params,
                "json": json,
            }
        )
        payload = self._responses.pop(0)
        return httpx.Response(
            int(payload.get("status_code", 200)),
            json=payload.get("json"),
            request=httpx.Request(method, url, params=params, json=json),
        )


def test_marketplace_client_lists_requests_and_checks_eligibility() -> None:
    captured_requests: list[dict[str, object]] = []
    responses = [
        {
            "json": {
                "items": [
                    {
                        "request_id": "req-1",
                        "status": "open",
                        "input_kind": "deployed_address",
                        "contract_address": "0x1000000000000000000000000000000000000001",
                        "chain_id": 84532,
                        "bounty_wei": 2_000_000_000_000_000_000,
                        "protocol_fee_wei": 100_000_000_000_000_000,
                        "filters": {
                            "minimum_stake_wei": 10_000_000_000_000_000,
                        },
                        "metadata": {
                            "confidence_hint": "high",
                        },
                    }
                ]
            }
        },
        {
            "json": {
                "request_id": "req-1",
                "auditor_service_id": "proof-of-audit-auditor",
                "eligible": True,
                "approximate": True,
                "minimum_stake_wei": 10_000_000_000_000_000,
                "reasons": ["Matches the current preview filters."],
            }
        },
    ]
    client = AuditRequestMarketplaceClient(
        base_url="http://127.0.0.1:8080",
        client_factory=lambda **kwargs: FakeHttpClient(
            responses=responses,
            requests=captured_requests,
            **kwargs,
        ),
    )

    requests = client.list_open_requests()
    assert len(requests) == 1
    assert requests[0].request_id == "req-1"
    assert requests[0].minimum_stake_wei == 10_000_000_000_000_000

    eligibility = client.get_request_eligibility(
        request_id="req-1",
        auditor_service_id="proof-of-audit-auditor",
    )
    assert eligibility.eligible is True
    assert "Matches the current preview filters." in eligibility.reasons
    assert captured_requests[0]["url"].endswith("/requests?status=open")
    assert captured_requests[1]["params"] == {"auditor": "proof-of-audit-auditor"}
def test_participation_loop_logs_and_skips_replays() -> None:
    class StubClient:
        def list_open_requests(self):  # type: ignore[no-untyped-def]
            from proof_of_audit_agent.request_participation import AuditRequest

            return [
                AuditRequest(
                    request_id="req-1",
                    status="open",
                    input_kind="deployed_address",
                    contract_address="0x1000000000000000000000000000000000000001",
                    chain_id=84532,
                    entry_contract="Vault",
                    bounty_wei=2_000_000_000_000_000_000,
                    protocol_fee_wei=100_000_000_000_000_000,
                    minimum_stake_wei=10_000_000_000_000_000,
                    response_window_end="2026-03-30T00:00:00Z",
                    created_at="2026-03-27T10:00:00Z",
                    metadata={"confidence_hint": "high"},
                )
            ]

        def get_request_eligibility(self, *, request_id: str, auditor_service_id: str):  # type: ignore[no-untyped-def]
            from proof_of_audit_agent.request_participation import RequestEligibility

            assert request_id == "req-1"
            assert auditor_service_id == "proof-of-audit-auditor"
            return RequestEligibility(
                request_id=request_id,
                auditor_service_id=auditor_service_id,
                eligible=True,
                approximate=True,
                minimum_stake_wei=10_000_000_000_000_000,
                reasons=("Matches the current preview filters.",),
            )

        def submit_draft_claim(self, **_: object) -> str:
            raise AssertionError("submit_draft_claim should not run in log-only mode")

    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "request-decisions.jsonl"
        loop = AuditRequestParticipationLoop(
            client=StubClient(),  # type: ignore[arg-type]
            auditor_service_id="proof-of-audit-auditor",
            policy=ParticipationPolicy(
                minimum_bounty_wei=1_000_000_000_000_000_000,
                max_concurrent_audits=2,
            ),
            decision_store=JsonlDecisionStore(log_path),
            submission_enabled=False,
        )

        first_pass = loop.run_once()
        second_pass = loop.run_once()

        assert len(first_pass) == 1
        assert first_pass[0].action == "would_submit"
        assert first_pass[0].suggested_stake_wei == 1_000_000_000_000_000_000
        assert second_pass == []


def test_participation_loop_can_submit_draft_claims() -> None:
    class StubClient:
        def __init__(self) -> None:
            self.submissions: list[tuple[str, str]] = []

        def list_open_requests(self):  # type: ignore[no-untyped-def]
            from proof_of_audit_agent.request_participation import AuditRequest

            return [
                AuditRequest(
                    request_id="req-2",
                    status="open",
                    input_kind="deployed_address",
                    contract_address="0x1000000000000000000000000000000000000002",
                    chain_id=84532,
                    entry_contract="Treasury",
                    bounty_wei=3_000_000_000_000_000_000,
                    protocol_fee_wei=100_000_000_000_000_000,
                    minimum_stake_wei=10_000_000_000_000_000,
                    response_window_end=None,
                    created_at="2026-03-27T10:30:00Z",
                    metadata={"confidence_hint": "medium"},
                )
            ]

        def get_request_eligibility(self, *, request_id: str, auditor_service_id: str):  # type: ignore[no-untyped-def]
            from proof_of_audit_agent.request_participation import RequestEligibility

            return RequestEligibility(
                request_id=request_id,
                auditor_service_id=auditor_service_id,
                eligible=True,
                approximate=True,
                minimum_stake_wei=10_000_000_000_000_000,
                reasons=("Matches the current preview filters.",),
            )

        def submit_draft_claim(self, *, request, auditor_service_id: str, submitted_by: str):  # type: ignore[no-untyped-def]
            self.submissions.append((request.request_id, auditor_service_id))
            assert submitted_by == "listener:proof-of-audit-auditor"
            return "audit-123"

    with tempfile.TemporaryDirectory() as tmpdir:
        client = StubClient()
        loop = AuditRequestParticipationLoop(
            client=client,  # type: ignore[arg-type]
            auditor_service_id="proof-of-audit-auditor",
            policy=ParticipationPolicy(),
            decision_store=JsonlDecisionStore(Path(tmpdir) / "request-decisions.jsonl"),
            submission_enabled=True,
        )

        decisions = loop.run_once()

        assert len(decisions) == 1
        assert decisions[0].action == "submitted"
        assert decisions[0].submitted_audit_id == "audit-123"
        assert client.submissions == [("req-2", "proof-of-audit-auditor")]
