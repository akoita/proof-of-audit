# Agent-Forge Service Contract

This document defines the intended HTTP contract between Proof-of-Audit and an
externally deployed `agent-forge` service.

It is a design target for:

- Proof-of-Audit issue [#238](https://github.com/akoita/proof-of-audit/issues/238)
- agent-forge issue [#90](https://github.com/akoita/agent-forge/issues/90)
- [OpenAPI draft](./AGENT_FORGE_SERVICE_OPENAPI.yaml)

## Goals

- keep Proof-of-Audit as the user-facing orchestration layer
- keep `agent-forge` generic enough to serve more than one client
- avoid baking chain-specific explorer logic into `agent-forge`
- define a stable machine contract instead of relying on terminal-oriented CLI output

## Boundary

Proof-of-Audit remains responsible for:

- validating user submissions
- resolving verified source for `deployed_address` submissions
- choosing the audit profile and policy
- mapping remote run state into audit lifecycle state
- publishing and challenging on-chain claims

The external `agent-forge` service remains responsible for:

- accepting prepared source material
- running the canonical coding-agent runtime in a compatible sandbox
- producing machine-readable run status and report artifacts
- exposing logs and error state for downstream consumers

This means a `deployed_address` flow should normally look like this:

1. Proof-of-Audit resolves verified source from Sourcify or an explorer.
2. Proof-of-Audit materializes that source into an archive or repository bundle.
3. Proof-of-Audit submits the prepared source plus target metadata to `agent-forge`.
4. `agent-forge` returns a run id and later a machine-readable report.

The external service should not be required to know how to query Base Sepolia,
Basescan, or Proof-of-Audit-specific fixture manifests.

## Versioning

- Base path: `/v1`
- Every response should include a schema version field when returning structured run or report data.
- Breaking changes require a new versioned path or report schema id.

## Authentication

This contract assumes service-to-service authentication.

Minimum expectation:

- `Authorization: Bearer <token>`

Preferred production shape:

- workload identity or signed service-to-service token between Proof-of-Audit and the hosted `agent-forge` service

## Run lifecycle

The service exposes these run states:

- `accepted`
- `queued`
- `running`
- `completed`
- `failed`
- `cancelled`

These states are transport-neutral and should not encode Proof-of-Audit audit
status directly.

## Endpoint summary

### `POST /v1/runs`

Accept a new machine client run request.

Example request:

```json
{
  "schema_version": "agent-forge-run-request-v1",
  "client": {
    "name": "proof-of-audit",
    "request_id": "audit-123",
    "service_id": "proof-of-audit-auditor"
  },
  "profile": {
    "id": "proof-of-audit-solidity-v1",
    "report_schema": "proof-of-audit-report-v1",
    "max_iterations": 12
  },
  "source": {
    "kind": "archive_uri",
    "uri": "gs://proof-of-audit-source-bundles/bundles/audit-123.zip",
    "archive_format": "zip",
    "entry_contract": "VulnerableBank",
    "source_digest": "sha256:abc123"
  },
  "target": {
    "submission_kind": "deployed_address",
    "network": "base-sepolia",
    "chain_id": 84532,
    "contract_address": "0xEbB43aa379270bcBbffDf33656AC37eBD7C81A11"
  },
  "artifacts": {
    "result_delivery": "pull",
    "include_logs": true
  }
}
```

Notes:

- `source.kind` is intentionally generic.
- Proof-of-Audit should prefer prepared archives or repository snapshots over raw deployed-address resolution requests.
- `profile.id` selects the task template and report expectations.

Success response:

```json
{
  "schema_version": "agent-forge-run-v1",
  "run_id": "run_01JXYZ",
  "status": "accepted",
  "status_url": "/v1/runs/run_01JXYZ",
  "report_url": "/v1/runs/run_01JXYZ/report",
  "logs_url": "/v1/runs/run_01JXYZ/logs",
  "created_at": "2026-03-25T10:30:00Z"
}
```

Validation failures should use `4xx` responses with stable error codes.

### `GET /v1/runs/{run_id}`

Read the latest state for a submitted run.

Example response:

```json
{
  "schema_version": "agent-forge-run-v1",
  "run_id": "run_01JXYZ",
  "status": "completed",
  "created_at": "2026-03-25T10:30:00Z",
  "started_at": "2026-03-25T10:30:04Z",
  "completed_at": "2026-03-25T10:30:21Z",
  "client": {
    "name": "proof-of-audit",
    "request_id": "audit-123",
    "service_id": "proof-of-audit-auditor"
  },
  "profile": {
    "id": "proof-of-audit-solidity-v1",
    "report_schema": "proof-of-audit-report-v1"
  },
  "report_url": "/v1/runs/run_01JXYZ/report",
  "logs_url": "/v1/runs/run_01JXYZ/logs",
  "error": null
}
```

If the run fails, `error` should become a structured object:

```json
{
  "code": "sandbox_start_failed",
  "message": "Docker sandbox could not start for this run.",
  "retryable": true
}
```

### `GET /v1/runs/{run_id}/report`

Return the machine-readable report artifact for a completed run.

This endpoint should fail clearly if the run is not yet completed.

### `GET /v1/runs/{run_id}/logs`

Return or redirect to log artifacts for debugging and auditability.

This is optional for end users but important for operators.

## Report schema

Proof-of-Audit needs a stable report contract, not free-form CLI output.

Target response shape:

```json
{
  "schema_version": "proof-of-audit-report-v1",
  "run_id": "run_01JXYZ",
  "summary": "Potential reentrancy after external call in withdraw().",
  "confidence": "medium",
  "benchmark_id": null,
  "target": {
    "submission_kind": "deployed_address",
    "network": "base-sepolia",
    "chain_id": 84532,
    "contract_address": "0xEbB43aa379270bcBbffDf33656AC37eBD7C81A11",
    "entry_contract": "VulnerableBank"
  },
  "findings": [
    {
      "finding_id": "agent-forge-live.reentrancy.withdraw",
      "title": "Potential reentrancy after external call",
      "severity": "high",
      "category": "reentrancy",
      "description": "This function performs an external call before updating balance-like state.",
      "impact": "A malicious callee may re-enter before state is fully updated and drain funds.",
      "recommendation": "Apply checks-effects-interactions or add a reentrancy guard before the external call.",
      "confidence": "medium",
      "detector": "agent_forge.static.reentrancy",
      "affected_function": "withdraw()",
      "source_path": "src/VulnerableBank.sol",
      "start_line": 13,
      "end_line": 15,
      "evidence_uri": null
    }
  ],
  "stats": {
    "finding_count": 1,
    "max_severity": "high",
    "severity_breakdown": {
      "critical": 0,
      "high": 1,
      "medium": 0,
      "low": 0
    }
  },
  "provenance": {
    "profile_id": "proof-of-audit-solidity-v1",
    "source_digest": "sha256:abc123"
  }
}
```

Compatibility rules:

- `finding_id` must be stable for the same normalized finding
- severity must map cleanly into Proof-of-Audit severity buckets
- `findings` may be empty, but the service must still return a completed report
- missing reports must be treated as execution failure, not implicit no-findings

## Error model

The service should use stable error codes so Proof-of-Audit can distinguish:

- `invalid_request`
- `unsupported_profile`
- `unsupported_source_kind`
- `source_fetch_failed`
- `sandbox_start_failed`
- `sandbox_execution_failed`
- `report_generation_failed`
- `policy_denied`
- `unauthorized`
- `quota_exceeded`

Each error should include:

- `code`
- `message`
- `retryable`

## Delivery model

Preferred first implementation:

- `POST /v1/runs`
- `GET /v1/runs/{run_id}`
- `GET /v1/runs/{run_id}/report`

This pull-based model is simpler than webhooks and is enough for Proof-of-Audit.

Webhooks can be added later if a real need appears.

## Non-goals

This contract does not require the hosted `agent-forge` service to:

- publish claims on-chain
- resolve blockchain explorer metadata on behalf of clients
- understand Proof-of-Audit settlement rules
- mirror Proof-of-Audit audit ids or statuses exactly

Those remain client responsibilities.
