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

## Contract surface

The settlement contract now exposes:

- `createAuditRequest(target, bountyAmount, responseWindow, eligibilityConfig)`
- `getAuditRequest(requestId)`
- `auditRequestState(requestId)`
- `expireAuditRequest(requestId)`
- `refundExpiredAuditRequest(requestId)`

## Events

The contract emits:

- `AuditRequested`
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

## Indexing model

The contract event is the durable source of truth.

In this repo, the API currently indexes requests that were created through this API
instance and persists a local request catalog for polling clients. Each read re-syncs
the request status and escrow metadata from the contract when chain access is
configured.

That keeps the implementation small for V1 while preserving a path toward a dedicated
event indexer later.
