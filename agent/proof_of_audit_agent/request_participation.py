from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from hashlib import sha256
import json
from pathlib import Path
import time
from typing import Any, Callable
from urllib.parse import urljoin

import httpx


@dataclass(frozen=True)
class AuditRequest:
    request_id: str
    status: str
    input_kind: str
    contract_address: str
    chain_id: int | None
    entry_contract: str | None
    bounty_wei: int
    protocol_fee_wei: int
    minimum_stake_wei: int
    response_window_end: str | None
    created_at: str | None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "AuditRequest":
        filters = payload.get("filters")
        if not isinstance(filters, dict):
            filters = {}
        metadata = payload.get("metadata")
        return cls(
            request_id=str(payload.get("request_id") or "").strip(),
            status=str(payload.get("status") or "").strip().lower(),
            input_kind=str(payload.get("input_kind") or "deployed_address").strip().lower(),
            contract_address=str(payload.get("contract_address") or "").strip().lower(),
            chain_id=int(payload["chain_id"]) if payload.get("chain_id") is not None else None,
            entry_contract=(
                str(payload.get("entry_contract")).strip()
                if payload.get("entry_contract") is not None
                else None
            ),
            bounty_wei=max(int(payload.get("bounty_wei") or 0), 0),
            protocol_fee_wei=max(int(payload.get("protocol_fee_wei") or 0), 0),
            minimum_stake_wei=max(int(filters.get("minimum_stake_wei") or 0), 0),
            response_window_end=(
                str(payload.get("response_window_end")).strip()
                if payload.get("response_window_end") is not None
                else None
            ),
            created_at=(
                str(payload.get("created_at")).strip()
                if payload.get("created_at") is not None
                else None
            ),
            metadata=dict(metadata) if isinstance(metadata, dict) else {},
        )

    def fingerprint(self) -> str:
        payload = {
            "request_id": self.request_id,
            "status": self.status,
            "input_kind": self.input_kind,
            "contract_address": self.contract_address,
            "chain_id": self.chain_id,
            "entry_contract": self.entry_contract,
            "bounty_wei": self.bounty_wei,
            "protocol_fee_wei": self.protocol_fee_wei,
            "minimum_stake_wei": self.minimum_stake_wei,
            "response_window_end": self.response_window_end,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }
        return sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RequestEligibility:
    request_id: str
    auditor_service_id: str
    eligible: bool
    approximate: bool
    minimum_stake_wei: int
    reasons: tuple[str, ...]

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "RequestEligibility":
        reasons = payload.get("reasons")
        return cls(
            request_id=str(payload.get("request_id") or "").strip(),
            auditor_service_id=str(payload.get("auditor_service_id") or "").strip(),
            eligible=bool(payload.get("eligible")),
            approximate=bool(payload.get("approximate", True)),
            minimum_stake_wei=max(int(payload.get("minimum_stake_wei") or 0), 0),
            reasons=tuple(str(reason) for reason in reasons) if isinstance(reasons, list) else tuple(),
        )


@dataclass(frozen=True)
class ParticipationPolicy:
    minimum_bounty_wei: int = 0
    max_concurrent_audits: int = 2
    opportunity_cost_wei: int = 0
    low_confidence_stake_fraction: float = 0.10
    medium_confidence_stake_fraction: float = 0.25
    high_confidence_stake_fraction: float = 0.50
    default_stake_confidence: str = "medium"

    def confidence_fraction(self, confidence: str) -> float:
        normalized = confidence.strip().lower()
        if normalized == "high":
            return self.high_confidence_stake_fraction
        if normalized == "low":
            return self.low_confidence_stake_fraction
        return self.medium_confidence_stake_fraction


@dataclass(frozen=True)
class ParticipationDecision:
    request_id: str
    action: str
    reason: str
    eligible: bool
    bounty_wei: int
    protocol_fee_wei: int
    opportunity_score_wei: int
    suggested_stake_wei: int
    request_fingerprint: str
    submitted_audit_id: str | None = None
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class JsonlDecisionStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._records = self._load_records()

    def _load_records(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        records: list[dict[str, Any]] = []
        for raw_line in self.path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            records.append(json.loads(line))
        return records

    def has_decision(self, request_id: str, request_fingerprint: str) -> bool:
        return any(
            str(record.get("request_id")) == request_id
            and str(record.get("request_fingerprint")) == request_fingerprint
            for record in self._records
        )

    def active_submission_count(self) -> int:
        return sum(
            1
            for record in self._records
            if str(record.get("action")) in {"would_submit", "submitted"}
        )

    def append(self, decision: ParticipationDecision) -> None:
        self._records.append(decision.to_dict())
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(decision.to_dict(), sort_keys=True) + "\n")


class AuditRequestMarketplaceClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_token: str | None = None,
        request_timeout_seconds: float = 30.0,
        client_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token
        self.request_timeout_seconds = request_timeout_seconds
        self._client_factory = client_factory or httpx.Client

    def list_open_requests(self) -> list[AuditRequest]:
        payload = self._request("GET", "/requests?status=open")
        items = payload.get("items")
        if not isinstance(items, list):
            return []
        return [AuditRequest.from_payload(item) for item in items if isinstance(item, dict)]

    def get_request_eligibility(
        self,
        *,
        request_id: str,
        auditor_service_id: str,
    ) -> RequestEligibility:
        payload = self._request(
            "GET",
            f"/requests/{request_id}/eligibility",
            params={"auditor": auditor_service_id},
        )
        return RequestEligibility.from_payload(payload)

    def submit_draft_claim(
        self,
        *,
        request: AuditRequest,
        auditor_service_id: str,
        submitted_by: str,
    ) -> str:
        payload = {
            "input_kind": request.input_kind,
            "service_id": auditor_service_id,
            "contract_address": request.contract_address,
            "chain_id": request.chain_id,
            "entry_contract": request.entry_contract,
            "submitted_by": submitted_by,
        }
        created = self._request("POST", "/audits", json=payload)
        audit_id = str(created.get("id") or "").strip()
        if not audit_id:
            raise ValueError("audit creation response did not include id")
        return audit_id

    def _request(
        self,
        method: str,
        path_or_url: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        headers = {"accept": "application/json"}
        if json is not None:
            headers["content-type"] = "application/json"
        if self.api_token:
            headers["authorization"] = f"Bearer {self.api_token}"
        with self._client_factory(timeout=self.request_timeout_seconds, headers=headers) as client:
            response = client.request(
                method,
                self._absolute_url(path_or_url),
                params=params,
                json=json,
            )
        if response.status_code >= 400:
            raise ValueError(self._error_message(response))
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("marketplace API returned non-object JSON")
        return payload

    def _absolute_url(self, path_or_url: str) -> str:
        if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
            return path_or_url
        return urljoin(f"{self.base_url}/", path_or_url.lstrip("/"))

    def _error_message(self, response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            return response.text.strip() or f"marketplace API request failed with {response.status_code}"
        if isinstance(payload, dict):
            detail = payload.get("detail")
            if isinstance(detail, dict):
                message = str(detail.get("message") or detail.get("error") or "").strip()
                if message:
                    return message
            message = str(payload.get("message") or payload.get("error") or "").strip()
            if message:
                return message
        return response.text.strip() or f"marketplace API request failed with {response.status_code}"


class AuditRequestParticipationLoop:
    def __init__(
        self,
        *,
        client: AuditRequestMarketplaceClient,
        auditor_service_id: str,
        policy: ParticipationPolicy,
        decision_store: JsonlDecisionStore,
        submission_enabled: bool = False,
        submitted_by: str | None = None,
        logger: Callable[[ParticipationDecision], None] | None = None,
    ) -> None:
        self.client = client
        self.auditor_service_id = auditor_service_id
        self.policy = policy
        self.decision_store = decision_store
        self.submission_enabled = submission_enabled
        self.submitted_by = submitted_by or f"listener:{auditor_service_id}"
        self.logger = logger

    def run_once(self) -> list[ParticipationDecision]:
        decisions: list[ParticipationDecision] = []
        active_audits = self.decision_store.active_submission_count()
        for request in self.client.list_open_requests():
            fingerprint = request.fingerprint()
            if self.decision_store.has_decision(request.request_id, fingerprint):
                continue

            eligibility = self.client.get_request_eligibility(
                request_id=request.request_id,
                auditor_service_id=self.auditor_service_id,
            )
            decision = self._decide(
                request=request,
                eligibility=eligibility,
                active_audits=active_audits,
            )
            if decision.action == "would_submit" and self.submission_enabled:
                audit_id = self.client.submit_draft_claim(
                    request=request,
                    auditor_service_id=self.auditor_service_id,
                    submitted_by=self.submitted_by,
                )
                decision = replace(
                    decision,
                    action="submitted",
                    reason="Submitted a draft audit through the API-mediated flow.",
                    submitted_audit_id=audit_id,
                )
                active_audits += 1
            elif decision.action in {"would_submit", "submitted"}:
                active_audits += 1

            self.decision_store.append(decision)
            if self.logger is not None:
                self.logger(decision)
            decisions.append(decision)
        return decisions

    def _decide(
        self,
        *,
        request: AuditRequest,
        eligibility: RequestEligibility,
        active_audits: int,
    ) -> ParticipationDecision:
        suggested_stake = self._suggested_stake_wei(request)
        opportunity_score = (
            request.bounty_wei
            - request.protocol_fee_wei
            - self.policy.opportunity_cost_wei
        )
        if request.input_kind != "deployed_address":
            return self._decision(
                request=request,
                action="skip",
                reason="Current participation loop only supports deployed_address requests.",
                eligibility=eligibility,
                opportunity_score_wei=opportunity_score,
                suggested_stake_wei=suggested_stake,
            )
        if not eligibility.eligible:
            return self._decision(
                request=request,
                action="skip",
                reason="Eligibility pre-check rejected this request.",
                eligibility=eligibility,
                opportunity_score_wei=opportunity_score,
                suggested_stake_wei=suggested_stake,
            )
        if request.bounty_wei < self.policy.minimum_bounty_wei:
            return self._decision(
                request=request,
                action="skip",
                reason="Bounty is below the configured minimum threshold.",
                eligibility=eligibility,
                opportunity_score_wei=opportunity_score,
                suggested_stake_wei=suggested_stake,
            )
        if active_audits >= self.policy.max_concurrent_audits:
            return self._decision(
                request=request,
                action="skip",
                reason="Maximum concurrent audit capacity is already in use.",
                eligibility=eligibility,
                opportunity_score_wei=opportunity_score,
                suggested_stake_wei=suggested_stake,
            )
        if opportunity_score <= 0:
            return self._decision(
                request=request,
                action="skip",
                reason="Opportunity-cost filter rejected this request.",
                eligibility=eligibility,
                opportunity_score_wei=opportunity_score,
                suggested_stake_wei=suggested_stake,
            )
        return self._decision(
            request=request,
            action="would_submit",
            reason="Request passed the current participation policy.",
            eligibility=eligibility,
            opportunity_score_wei=opportunity_score,
            suggested_stake_wei=suggested_stake,
        )

    def _suggested_stake_wei(self, request: AuditRequest) -> int:
        confidence = str(
            request.metadata.get("stake_confidence")
            or request.metadata.get("confidence_hint")
            or self.policy.default_stake_confidence
        )
        fraction = self.policy.confidence_fraction(confidence)
        return max(request.minimum_stake_wei, int(request.bounty_wei * fraction))

    def _decision(
        self,
        *,
        request: AuditRequest,
        action: str,
        reason: str,
        eligibility: RequestEligibility,
        opportunity_score_wei: int,
        suggested_stake_wei: int,
    ) -> ParticipationDecision:
        return ParticipationDecision(
            request_id=request.request_id,
            action=action,
            reason=reason,
            eligible=eligibility.eligible,
            bounty_wei=request.bounty_wei,
            protocol_fee_wei=request.protocol_fee_wei,
            opportunity_score_wei=opportunity_score_wei,
            suggested_stake_wei=suggested_stake_wei,
            request_fingerprint=request.fingerprint(),
        )
