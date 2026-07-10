# AuditRequest Protocol

> **Public network status (see [#303](https://github.com/akoita/proof-of-audit/issues/303)
> and [DEPLOYED_VERSION.md](./DEPLOYED_VERSION.md)):** the live Base Sepolia
> `ProofOfAudit` deployment predates this marketplace subsystem. On public
> networks, treat `AuditRequest` / marketplace settlement as **undeployed**.
> The design below describes **current source + local Anvil / API preview**
> behavior, not the bytecode at `0xf2da3947d028b85e597fe1df4633a87ef4a85f24`.

`#217` introduces a marketplace request primitive alongside the legacy single-auditor
`publishAudit` flow.

## Purpose

An `AuditRequest` is an ETH-backed bounty escrow created by the requester before any
auditor claim is published.

This is the foundation for the marketplace path:

- requester deposits bounty into the settlement contract
- request stays open for a fixed response window
- agents discover the request through the API
- later issues attach claims, eligibility enforcement, and payout logic to this request

## Backward compatibility

The legacy single-auditor path remains unchanged:

- `publishAudit`
- `challengeAudit`
- `resolveChallenge`
- `releaseStake`

`AuditRequest` is a parallel primitive, not a migration of the existing claim flow.

## State model

The request lifecycle is:

- `Open`
  - request exists
  - bounty is escrowed
  - response window is still active
- `Closed`
  - derived state once the response window has elapsed
  - no new claims should be accepted after this point
- `Expired`
  - terminal no-claim path
  - request was closed with zero claims and marked refundable
- `Settled`
  - request-level settlement accounting has been finalized
  - claim withdrawals and requester dust / zero-eligible refund now use pull-based withdrawals
  - the same terminal state is also used by the no-claim `Expired -> refund` path

For V1, `Closed` is derived from `responseWindowEnd` rather than requiring a separate
close transaction.

## Claim model

Marketplace claims are separate from the legacy single-auditor `publishAudit` path.

The contract now accepts request-bound claims through
`submitAuditRequestClaim(requestId, agentRegistry, agentId, reportHash, metadataHash, maxSeverity, findingCount)`.

Each claim carries:

- `claimId`
- `requestId`
- `auditor`
- `agentRegistry`
- `agentId`
- `stakeAmount`
- `reportHash`
- `metadataHash`
- `maxSeverity`
- `findingCount`
- `submittedAt`
- `state`
- optional dispute metadata once challenged:
  - `challengedAt`
  - `challengeBond`
  - `resolution`
  - `challenger`
  - `evidenceHash`

The current claim state model now covers bounded V1 dispute settlement:

- `Submitted`
  - claim was accepted while the parent request was `Open`
  - stake was escrowed with the claim
- `Challenged`
  - an eligible competing auditor opened a bonded dispute against the claim
- `Slashed`
  - terminal upheld-challenge path
  - the claim is ineligible for any later bounty distribution
- `Resolved`
  - terminal rejected-challenge path
  - the claim stays unslashed and remains eligible for later bounty settlement

## Contract surface

The settlement contract now exposes:

- `createAuditRequest(target, bountyAmount, responseWindow, eligibilityConfig, allowlistedAuditors)`
- `getAuditRequest(requestId)`
- `auditRequestState(requestId)`
- `submitAuditRequestClaim(requestId, agentRegistry, agentId, reportHash, metadataHash, maxSeverity, findingCount)`
- `challengeAuditRequestClaim(claimId, agentRegistry, agentId, evidenceHash)`
- `resolveAuditRequestClaimChallenge(claimId, upheld)`
- `getAuditRequestClaim(claimId)`
- `getAuditRequestClaimIds(requestId)`
- `classifyAuditRequestClaims(requestId, maxClaims)`
- `finalizeAuditRequestSettlement(requestId)`
- `getAuditRequestSettlement(requestId)`
- `getAuditRequestClaimSettlement(claimId)`
- `previewAuditRequestClaimSettlement(claimId)`
- `previewAuditRequestRefund(requestId)`
- `withdrawAuditRequestClaimSettlement(claimId)`
- `withdrawAuditRequestRefund(requestId)`
- `getAuditRequestAllowlistedAuditors(requestId)`
- `isAuditRequestAuditorAllowlisted(requestId, auditor)`
- `expireAuditRequest(requestId)`
- `refundExpiredAuditRequest(requestId)`

## Events

The contract emits:

- `AuditRequested`
- `AuditRequestClaimSubmitted`
- `AuditRequestClaimChallengeOpened`
- `AuditRequestClaimChallengeResolved`
- `AuditRequestSettlementFinalized`
- `AuditRequestClaimSettlementWithdrawn`
- `AuditRequestExpired`
- `AuditRequestRefunded`

The `AuditRequested` event carries the request target, bounty, response-window end,
and the stored eligibility config fields needed for off-chain indexing.

## Eligibility config in V1

`#221` wires the request filters into the claim-submission path.

The stored config fields are:

- `minimumStakeAmount`
- `allowlistEnabled`
- `identityRegistry`
- `requiredAgentId`

The allowlist itself is stored as a per-request `address => bool` mapping plus a getter
for the snapshotted address list. The `AuditRequested` event still emits an
`allowlistRoot`, but that value is now a commitment over the stored address snapshot,
not a service-id hash.

API callers still submit richer filter inputs:

- `allowed_service_ids`
- `required_identity_service_id`

At request creation time the API resolves those inputs into on-chain values:

- `allowed_service_ids` -> current owner addresses of those services' canonical
  `(agentRegistry, agentId)` identities
- `required_identity_service_id` -> one concrete `(identityRegistry, agentId)` pair

That means request creation snapshots the allowlist to owner addresses, while required
identity remains a live canonical identity check at claim submission time.

## Claim-time enforcement in V1

`submitAuditRequestClaim` now enforces all three V1 filters compositionally:

- minimum stake:
  `msg.value` must be at least `max(requiredStake, minimumStakeAmount)`
- allowlist mode:
  if enabled, `msg.sender` must be in the request's stored address allowlist
- required identity:
  if configured, the submitted `(agentRegistry, agentId)` must match the stored
  required identity

The contract also still enforces canonical identity ownership through
`ownerOf(agentId) == msg.sender`.

Relevant revert reasons are:

- `InsufficientRequestClaimStake`
- `RequestClaimNotAllowlisted`
- `RequestClaimIdentityRegistryMismatch`
- `RequestClaimAgentIdMismatch`
- `IdentityOwnerMismatch`
- `DuplicateRequestClaim`

## Cross-auditor challenge settlement in V1

`#220` adds a bounded request-claim dispute path without waiting for bounty
distribution design.

Challenge admission:

- the challenger must be a registered canonical identity
- the challenger must satisfy the same allowlist / required-identity constraints as
  a submitted request claim
- the challenger cannot challenge its own request claim
- the challenge must land before `submittedAt + challengeWindow`

Settlement rule:

- upheld:
  - claim moves to `Slashed`
  - gross payout is `claim.stakeAmount + challengeBond`
  - net beneficiary payout is `gross - resolutionFee`
  - beneficiary is the challenger
- rejected:
  - claim moves to `Resolved`
  - gross payout is only `challengeBond`
  - net beneficiary payout is `gross - resolutionFee`
  - beneficiary is the original claim auditor

This keeps payout obligations bounded to the challenged claim's escrow plus the
posted bond. A slashed claim is explicitly out of scope for later bounty
distribution. Resolution-fee accrual is emitted on the challenge-resolution
event and is withdrawable only through the treasury path.

## Pro-rata bounty settlement in V1

`#219` adds the first request-level distribution path for claims that survive the
full response/challenge lifecycle.

Settlement flow:

- once the request is `Closed` and each claim is no longer pending, anyone may call
  `classifyAuditRequestClaims(requestId, maxClaims)` in bounded batches
- classification marks each claim as either:
  - eligible
    - `Submitted` and its own challenge window elapsed without an open challenge
    - or `Resolved` after a rejected challenge
  - ineligible
    - `Slashed` after an upheld challenge
- once all claims are classified, anyone may call
  `finalizeAuditRequestSettlement(requestId)`

At finalization time the contract fixes:

- `eligibleClaimCount`
- `eligibleStakeTotal`
- `protocolFeeAmount`
- `distributableBountyAmount`

Claimant withdrawals are then pull-based:

- `withdrawAuditRequestClaimSettlement(claimId)`
  - only for eligible claims
  - returns the original claim stake
  - plus the pro-rata bounty share

For one eligible claim `i`:

```text
bountyShare_i = floor(distributableBounty * stake_i / eligibleStakeTotal)
```

Requester refunds are also pull-based:

- if zero eligible claims remain after all dispute outcomes are final:
  - `withdrawAuditRequestRefund(requestId)` returns the full request bounty
- if eligible claims exist:
  - each eligible claimant withdraws its computed share first
  - requester may then withdraw only the integer-division remainder dust

This keeps claimant withdrawals order-independent while preserving the closed
accounting model documented in
`MARKETPLACE_SETTLEMENT_ACCOUNTING.md`.

## Canonical identity rule

One request may only carry one submitted claim per canonical auditor identity.

The canonical identity key is the pair:

- `agentRegistry`
- `agentId`

At submission time the contract verifies that `ownerOf(agentId)` on the supplied
registry matches `msg.sender`. That prevents duplicate claims under the same
registered identity even if raw caller addresses or API paths differ.

## Indexing model

The contract event is the durable source of truth.

In this repo, the API currently indexes requests that were created through this API
instance and persists a local request catalog for polling clients. Each read re-syncs
the request status and escrow metadata from the contract when chain access is
configured.

That keeps the implementation small for V1 while preserving a path toward a dedicated
event indexer later.
