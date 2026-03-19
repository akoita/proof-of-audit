# Pluggable Auditor Integration

Proof-of-Audit can expose more than one auditor service. This document defines the
minimum contract an independent auditor must satisfy to plug into the application
without taking over the user-facing submission, challenge, and review flows.

## Design goals

- external auditors should integrate through a narrow, explicit boundary
- Proof-of-Audit should remain the orchestration layer for submission and challenge UX
- staking authority must be narrowly scoped
- discovery metadata must tell users how an auditor executes and settles claims

## Integration surfaces

There are three separate surfaces:

1. off-chain audit execution
2. stake-backed publication
3. service discovery metadata

They should not be conflated.

## 1. Off-chain audit execution contract

An external auditor must accept a Proof-of-Audit-style submission and return a
Proof-of-Audit-compatible report.

The minimum request shape is:

- `service_id`
- `input_kind`
- `chain_id`
- `contract_address`
- `fixture_id`
- `entry_contract`
- `source_bundle_uri`
- `source_bundle_label`
- `repository_url`
- `submitted_by`

The minimum response shape is:

- `benchmark_id`
- `contract_address`
- `summary`
- `findings`
- `supported_checks`
- `confidence`
- `report_hash`
- `metadata_hash`
- `max_severity`
- `finding_count`
- `severity_breakdown`

Compatibility rules:

- findings must keep stable ids
- severities must map into the existing Proof-of-Audit severity ladder
- evidence URIs must remain optional but, when present, should be durable
- `report_hash` and `metadata_hash` must be deterministic for the returned claim

Failure semantics:

- transport failures should be surfaced as execution failure, not silent fallback
- timeout behavior must be explicit in the service metadata
- unsupported submission modes must fail before execution starts

## 2. Staking and publication boundary

Proof-of-Audit should not receive unlimited authority over an external auditor's funds.

The intended boundary is:

- the external auditor owns stake capital
- the application may publish only the user-selected claim
- the delegated publication scope is explicit and revocable

There are two supported settlement models:

- `native_proof_of_audit`
  - the selected auditor publishes to the native `ProofOfAudit` contract
  - the staking adapter is the contract itself
- `adapter_delegated`
  - the selected auditor exposes a dedicated adapter contract that Proof-of-Audit calls
  - the adapter decides how stake is sourced and how publication is authorized

The adapter interface lives at:

- `/home/koita/dev/hackatons/proof-of-audit/contracts/src/interfaces/IProofOfAuditStakeAdapter.sol`

That interface is intentionally narrow:

- `publishStakedAudit(...)`
- `releaseStake(...)`
- `settlementContract()`

The `claimKey` in the publish request should bind the delegated publication call to
the exact claim selected by the user, so the application cannot publish arbitrary
claims with the same delegated permission.

## 3. Discovery metadata

An auditor service record must now describe:

- `execution_mode`
  - `local_worker` for the built-in worker path
  - `remote_http` for a remote execution service
- `execution_endpoint`
  - optional HTTP endpoint for remote execution
- `settlement_mode`
  - `native_proof_of_audit`
  - `adapter_delegated`
- `publication_mode`
  - `api_mediated`
  - `self_published`
- `staking_adapter_kind`
  - `native_proof_of_audit`
  - `proof_of_audit_stake_adapter`
- `staking_adapter_address`
- `staking_adapter_method`
- `publication_scope`
  - current MVP value: `submit_selected_claim`

These fields let the UI and API explain what kind of auditor a user is selecting
before any claim is created.

## Security expectations

- delegated publication must be scoped to one selected claim at a time
- revoked permissions must fail clearly during publish, not silently downgrade
- the application must not imply that a remote auditor is locally executed
- the challenge and payout lifecycle still terminates in the settlement layer, not in UI metadata

## What this does not do

This contract does not, by itself:

- add the user-facing auditor picker
- run real third-party remote auditors
- create challenger notifications

Those are separate follow-up issues.
