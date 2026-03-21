# Challenger Feed

Proof-of-Audit exposes a challenger-oriented lifecycle feed at `GET /challenger-feed`.

This feed is intended for challenger tooling that needs to discover:

- newly published audit claims
- newly opened challenges
- resolved challenge outcomes

The feed is built from audit records created by the publish, challenge, and resolve flows that also emit the contract lifecycle events (`AuditPublished`, `ChallengeOpened`, `ChallengeResolved`). It does not add a second on-chain source of truth; it packages the same lifecycle transitions into an application-level polling surface.

## Endpoint

`GET /challenger-feed?limit=50`

Query parameters:

- `limit`: optional, defaults to `50`, max `200`

## Feed item fields

Each item includes:

- `event_id`
- `event_kind`
- `event_timestamp`
- `audit_id`
- `published_audit_id`
- `service_id`
- `auditor_id`
- `auditor_name`
- `target_contract`
- `target_key`
- `publish_timestamp`
- `challenge_window_end`
- `current_state`
- `report_hash`
- `metadata_hash`
- `summary`
- `max_severity`
- `finding_count`
- relevant publish / challenge / resolve transaction hashes and URLs
- `verification_status`
- `verification_dossier_path` for machine-readable verifier output when a dossier exists
- `resolution` when the challenge has been resolved

## Event kinds

- `audit_published`
- `challenge_opened`
- `challenge_resolved`

## Reference consumer

Use [watch_challenger_feed.py](/home/koita/dev/hackatons/proof-of-audit/scripts/watch_challenger_feed.py) as a minimal polling consumer:

```bash
python scripts/watch_challenger_feed.py --api-base http://127.0.0.1:8080 --limit 20 --interval 15
```

The script prints newly observed events as they appear.

## Machine-readable verifier dossiers

Tooling that needs the full verifier substrate can follow the relative
`verification_dossier_path` from a feed item or audit record.

Endpoint:

`GET /audits/{audit_id}/challenge/dossier`

This returns the structured Challenge Verifier V2 dossier, including:

- integrity status
- execution metadata
- extracted claim
- comparison rationale and matched findings
- policy outcome, abstention, and confidence
- model and schema metadata
