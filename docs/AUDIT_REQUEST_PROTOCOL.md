# AuditRequest Protocol

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
  - escrow has left the request
  - for `#217`, this is the refund path after `Expired`

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

The current claim state model is intentionally small:

- `Submitted`
  - claim was accepted while the parent request was `Open`
  - stake was escrowed with the claim

## Contract surface

The settlement contract now exposes:

- `createAuditRequest(target, bountyAmount, responseWindow, eligibilityConfig)`
- `getAuditRequest(requestId)`
- `auditRequestState(requestId)`
- `submitAuditRequestClaim(requestId, agentRegistry, agentId, reportHash, metadataHash, maxSeverity, findingCount)`
- `getAuditRequestClaim(claimId)`
- `getAuditRequestClaimIds(requestId)`
- `expireAuditRequest(requestId)`
- `refundExpiredAuditRequest(requestId)`

## Events

The contract emits:

- `AuditRequested`
- `AuditRequestClaimSubmitted`
- `AuditRequestExpired`
- `AuditRequestRefunded`

The `AuditRequested` event carries the request target, bounty, response-window end,
and the stored eligibility config fields needed for off-chain indexing.

## Eligibility config in V1

`#217` stores an `EligibilityConfig` on the request so the marketplace path has a
stable parent object, but full enforcement is deferred to follow-up work in `#221`.

The current stored fields are:

- `minimumStakeAmount`
- `allowlistEnabled`
- `allowlistRoot`
- `identityRegistry`
- `requiredAgentId`

The API still exposes richer preview metadata, including service-id allowlists, for
off-chain participation heuristics. That preview metadata is not yet fully
chain-authoritative.

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
