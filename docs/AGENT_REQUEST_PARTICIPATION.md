# Agent Request Participation

`#223` starts from a polling, log-only participation loop instead of enabling live submissions by default.

## What exists now

- `POST /requests` creates an on-chain `AuditRequest` escrow and persists a local indexed record
- `GET /requests?status=open` returns indexed open request records for polling clients
- `GET /requests/{id}` returns one indexed request record with synced chain-backed status
- `POST /requests/{id}/claims` binds an existing draft audit to the request as an on-chain claim
- `GET /requests/{id}/claims` lists the request-bound claims known to this API instance
- `GET /requests/{id}/eligibility?auditor=...` applies the same preview filter logic used by the marketplace view
- `scripts/watch_audit_requests.py` polls those endpoints, evaluates heuristics, and records JSONL decisions
- `--submit` is opt-in; without it, the agent records `would_submit` decisions but does not create drafts

## Decision heuristics

- minimum bounty threshold
- maximum concurrent accepted requests
- opportunity-cost filter
- confidence-based stake sizing using request metadata such as `confidence_hint` or `stake_confidence`

## Idempotency and replay handling

- every discovered request is fingerprinted from the request payload fields that affect participation
- decisions are appended to a JSONL log, which doubles as the replay/idempotency store
- if the same `request_id` appears again with the same fingerprint, it is skipped
- if the request changes materially, the fingerprint changes and the agent re-evaluates it

## Current boundary

- request creation is now backed by the settlement contract from `#217`
- request-bound claim publication now exists through `POST /requests/{id}/claims`
- the polling loop still defaults to log-only mode; live submission remains opt-in
