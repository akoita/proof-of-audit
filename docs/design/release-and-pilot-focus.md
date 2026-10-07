# Release and pilot focus

- Status: Draft; not adopted
- Date: 2026-10-07
- Related: [current inventory](../strategy/STATE_OF_THE_PROJECT.md),
  [adopted roadmap](../strategy/ROADMAP.md), [vision](../strategy/VISION.md)

## Problem and drivers

The repository has useful escrow and evidence components, but recorded public
deployment evidence, operational readiness, and customer value remain incomplete.
The current roadmap makes bonded verdicts the first delivery wedge and places
recurring revenue in Phase 3. This proposal asks whether a narrower review
workflow and earlier paid validation would reduce product and maintenance risk.

This document preserves recommendations from the October project review. It is
not authorization to change the vision, adopt new technology, reopen parked
work, or implement a later phase before Phase 0 exits.

## Goals and boundaries

Prove that Solidity teams shipping upgrades repeatedly use a reproducible
security review. Preserve engine independence, explicit source scope, evidence
integrity, and human adjudication disclosure. Establish whether customers value
bonding enough to justify its funding and dispute process.

Marketplace expansion, persona demos, cross-chain settlement, TEE execution,
coverage pools, and a proprietary frontier audit engine remain outside this
proposal. It does not replace comprehensive audits or promise contract safety.

## Proposed sequencing

Complete Phase 0 with verifiable deployment claims, a recorded settlement cycle,
protected arbiter authority, transactional request storage, authenticated browser
operations, and recovery evidence. Conduct customer interviews during this work.

After Phase 0 exits, integrate one mature engine through one CLI or CI action.
Pin the repository and commit, analyze relevant dependencies, identify affected
findings, attach reproduction/provenance, and retain human review decisions.
Use optional testnet bonding to evaluate accountability without making it a
prerequisite for every pilot interaction.

Validate payment for the review/evidence workflow earlier than today's Phase 3
gate. Before adopting this sequencing, update the governing strategy documents
with the maintainer's decision and rationale. This draft alone changes no phase.

## Alternatives and trade-offs

Retaining the current bonded-first roadmap keeps the accountability hypothesis
central, but adds funding and adjudication dependencies before workflow demand
is demonstrated. The proposed sequence reduces those dependencies, at the cost
of testing bonding value separately and competing with existing review tools.

A scanner-only product is simpler, but existing CI tools already provide that
workflow. Evidence provenance, reproduction and review decisions need to add
measurable value beyond generating another findings list.

## Verification and decision gates

Suggested pilot thresholds are five relevant interviews, two pilot repositories,
ten non-fixture reviews, repeated partner use over four weeks, and one paid or
funded pilot. These are proposed thresholds, not validated market benchmarks.
Measure reviewer effort, finding precision, reproducibility, latency and run cost.

Test one precisely falsifiable claim class before binding settlement. Define
claim scope, invalidation conditions, payout ceiling, challenge window and
adjudication authority; uncertain cases must abstain. Independent review is
required before meaningful funds. A bond must not be presented as general loss
insurance.

If workflow demand exists without bonding demand, consider a documented reduction
in bonding scope. If repeat use and willingness to pay do not emerge, consider
maintaining the evidence components as an open-source integration rather than
expanding the marketplace.

## Open decisions

The maintainer must decide whether to change Phase 1 sequencing, which engine
and pilot teams to select, and what observed customer value justifies bonding.
No outcome or acceptance is recorded yet. Current delivery remains governed by
[Roadmap v2](../strategy/ROADMAP.md).
