# Agent Request Participation

`#223` starts from a polling, log-only participation loop instead of enabling live submissions by default.

## What exists now

- `POST /requests` creates an on-chain `AuditRequest` escrow and persists a local indexed record
- `GET /requests?status=open` returns indexed open request records for polling clients
- `GET /requests/{id}` returns one indexed request record with synced chain-backed status
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
- this is still ahead of `#218`, so agents discover requests but do not yet submit on-chain claims against them
- live submission, when enabled, creates a draft audit through the existing API flow; it does not yet bind the submission to an on-chain `AuditRequest`
