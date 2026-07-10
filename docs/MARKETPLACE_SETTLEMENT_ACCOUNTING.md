# Marketplace Settlement Accounting

This document freezes the payout/accounting model for the marketplace request
path before contract implementation for:

- `#219` pro-rata bounty distribution by stake weight
- `#222` protocol and resolution fees

It is intentionally narrower than the legacy single-auditor `publishAudit`
path. This spec only covers `AuditRequest` claim settlement.

## Scope

This spec applies after:

- `#217` request escrow exists
- `#218` multiple request-bound claims exist
- `#220` request-claim challenge and slash semantics exist

This spec does not change the legacy single-auditor `challengeAudit` /
`resolveChallenge` flow.

## Goal

Define one closed accounting model for all ETH that can move through one
request:

- requester bounty escrow
- auditor claim stakes
- challenge bonds
- challenger payouts
- returned claimant stakes
- bounty shares
- requester refunds
- protocol fees
- resolution fees

## Terms

For one request `R`:

- `B`
  - original bounty escrow for the request
- `S_i`
  - stake posted by claim `i`
- `C_j`
  - challenge bond posted by challenge `j`
- `eligible claim`
  - a request claim that survives final admissibility and settlement checks
- `slashed claim`
  - a request claim with an upheld challenge from `#220`
- `protocol fee rate`
  - the bounty-distribution fee rate from `#222`
- `resolution fee rate`
  - the dispute-payout fee rate from `#222`

## Final claim classification

A request claim is final for settlement only when the parent request response
window has closed and the claim is in one of these classes:

- `eligible`
  - claim state is `Submitted` and its individual challenge window has elapsed
    with no opened challenge
  - or claim state is `Resolved` after a rejected challenge
- `ineligible`
  - claim state is `Slashed`
- `pending`
  - claim state is `Challenged`
  - or claim state is `Submitted` but its individual challenge window has not
    elapsed yet

The request may not enter final settlement while any claim is still `pending`.

This is the precise meaning of "survived the challenge window":

- the claim is not slashed
- there is no unresolved open challenge against it
- its own `submittedAt + challengeWindow` has passed, unless a rejected challenge
  already finalized it as `Resolved`

## Settlement outputs

After finalization, the request can produce only these outputs:

- claimant withdrawal:
  - returned stake
  - plus bounty share, if eligible
- requester refund:
  - full bounty when zero eligible claims remain
  - or residual dust from integer division after all claimant withdrawals
- treasury withdrawal:
  - accumulated protocol fees
  - accumulated resolution fees

All settlement outputs must use pull-based withdrawals.

## Fee rules

### Protocol fee

The protocol fee applies only to the bounty distribution path.

Rule:

- if `eligibleStakeTotal > 0`
  - `protocolFee = floor(B * protocolFeeRate / FEE_DENOMINATOR)`
- else
  - `protocolFee = 0`

This means:

- pure no-claim expiry refunds pay no protocol fee
- zero-eligible-after-disputes refunds also pay no protocol fee

### Resolution fee

The resolution fee applies only when a challenge resolution causes an economic
transfer.

For each challenge payout `grossChallengePayout_j`:

- `resolutionFee_j = floor(grossChallengePayout_j * resolutionFeeRate / FEE_DENOMINATOR)`
- `beneficiaryNet_j = grossChallengePayout_j - resolutionFee_j`

No resolution fee is charged when there is no payout event.

## Challenge payout model

This spec preserves the bounded dispute semantics from `#220`.

For a challenged request claim:

- upheld challenge:
  - gross payout = `claim stake + challenge bond`
  - beneficiary = challenger
  - claim becomes `Slashed`
- rejected challenge:
  - gross payout = `challenge bond`
  - beneficiary = challenged claim auditor
  - claim becomes `Resolved`

Resolution fees, when implemented, are deducted from these gross payouts rather
than added on top of them.

## Bounty distribution model

Let:

- `E` be the set of final eligible claims for the request
- `eligibleStakeTotal = sum(S_i for i in E)`

If `eligibleStakeTotal == 0`:

- no bounty is distributed to auditors
- `protocolFee = 0`
- requester can withdraw the full remaining bounty escrow for the request

If `eligibleStakeTotal > 0`:

- `distributableBounty = B - protocolFee`
- each eligible claim `i` has:

```text
bountyShare_i = floor(distributableBounty * S_i / eligibleStakeTotal)
```

- each eligible claimant withdraws:

```text
claimWithdrawal_i = S_i + bountyShare_i
```

- ineligible/slashed claims withdraw nothing from request settlement

## Rounding and dust

Integer division creates deterministic remainder:

```text
distributionDust = distributableBounty - sum(bountyShare_i for i in E)
```

This dust is not an implicit fee.

Rule:

- each eligible claimant always receives the floor-computed share above
- after all eligible claimant withdrawals are complete, the requester may
  withdraw `distributionDust`

This keeps claimant withdrawals order-independent and avoids hidden fee drift.

## Closed payout invariant

For one request, the bounty accounting must satisfy:

```text
B = protocolFee + requesterRefund + sum(bountyShare_i for i in E)
```

Where:

- `requesterRefund`
  - is `B` when `E` is empty
  - otherwise is only the post-distribution dust remainder

Claim-stake and bond accounting must satisfy:

```text
sum(all claim stakes) + sum(all challenge bonds)
= sum(returned eligible claim stakes)
+ sum(gross challenge payouts)
```

And each gross challenge payout splits as:

```text
grossChallengePayout_j = beneficiaryNet_j + resolutionFee_j
```

Combined request-wide conservation:

```text
B
+ sum(all claim stakes)
+ sum(all challenge bonds)
= requesterRefund
+ sum(claimant withdrawals)
+ sum(beneficiaryNet challenge payouts)
+ protocolFee
+ sum(resolution fees)
```

No other ETH sink or source is allowed inside the request settlement path.

The invariant test suite models request creation, claim submission, claim
challenges, challenge resolution, batched classification, finalization,
claimant withdrawals, requester refunds, and fee withdrawals. It tracks all ETH
deposited into the contract and asserts that the live contract balance plus
observed payouts and accrued/withdrawn fees always equals total deposited ETH.

## Pull-withdrawal model

The settlement path should be implemented with three withdrawal families:

- `withdrawClaimSettlement(claimId)`
  - only for eligible claims
  - pays returned stake + bounty share
- `withdrawRequesterRefund(requestId)`
  - pays zero-eligible refund or final distribution dust
- `withdrawFees()`
  - treasury-only
  - pays accumulated protocol and resolution fees

Challenge payouts from `#220` may remain immediate or may be refactored into a
pull path, but the accounting above must stay identical.

## Gas-bound settlement design

Do not require one unbounded loop over every claim in a single transaction.

Acceptable shape:

- batch finalization that classifies claims and accumulates `eligibleStakeTotal`
- one request-level finalize step after all claims are classified
- individual pull withdrawals after finalization

This keeps per-call gas bounded while still supporting arbitrarily large claim
sets over multiple transactions.

## Minimal request-level primitives implied by this spec

The eventual contract implementation will need request-level accounting fields
equivalent to:

- whether settlement classification is complete
- how many claims have been classified
- final `eligibleStakeTotal`
- final `protocolFee`
- final `distributableBounty`
- cumulative claimant bounty withdrawn
- requester refund withdrawn flag
- per-claim withdrawal claimed flag
- treasury fee accumulator

Exact field names can differ, but the invariant above may not.

## API implications

After implementation:

- request detail should expose whether settlement is pending or finalized
- request claim detail should expose whether the claim is eligible, slashed, or
  already withdrawn
- `/config` should expose protocol and resolution fee parameters only once the
  contract is the source of truth

## Recommended implementation order

1. Land contract primitives for request finalization and pull withdrawals
2. Land fee parameters and treasury accumulation on the same branch/tranche
3. Expose finalized settlement fields through the API
4. Add contract and API tests for:
   - single eligible claimant
   - multiple eligible claimants with unequal stake
   - zero eligible after all claims are slashed
   - rejected challenges that preserve claimant eligibility
   - protocol fee and resolution fee rounding behavior
