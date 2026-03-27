# Audit Snapshot Semantics

This note defines how Proof-of-Audit should treat deployed-address audits as
claims about a specific chain snapshot rather than about a mutable address over
time.

## Problem

Today a deployed-address audit is identified primarily by:

- `chain_id`
- `contract_address`

That is not enough to make a published claim reproducible or challengeable when:

- the target is upgradeable
- initialization happens after audit start
- the contract state changes materially before publish
- executable challenges run against a later head rather than the state the audit
  actually evaluated

Without a pinned snapshot, the system is effectively making a claim about a
moving target.

## Core Rule

A deployed-address audit claim should mean:

> this auditor evaluated target `T` on chain `C` at snapshot block `B`, against
> the code identity and storage-visible chain state that existed at `B`

It should **not** mean:

> this address is correct forever, regardless of later upgrades or state changes

## Required Snapshot Fields

At audit start, the system should capture and persist:

- `snapshot_block_number`
- `snapshot_block_hash`
- `target_address`
- `target_code_hash_at_snapshot`
- `chain_id`

For upgradeable targets, the system should also capture:

- `implementation_address_at_snapshot`
- `implementation_code_hash_at_snapshot`
- `proxy_kind`

If the system cannot resolve proxy identity with confidence, it should say so
explicitly and downgrade the target identity guarantees rather than implying a
strong immutable claim.

## Publish Semantics

Publication should bind to the snapshot metadata.

Recommended V1 rule:

- a published claim is about `snapshot_block_number`
- if the target code identity changed between audit start and publish, the API
  should either reject publish or require an explicit user acknowledgement that
  the claim is stale and snapshot-bound

Preferred behavior:

- reject publish when code identity changed before publish
- require a fresh audit for the new target identity

That keeps the trust model simpler and avoids publishing obviously stale claims.

## Challenge Semantics

Executable challenge verification should run against the same snapshot used by
the audited claim.

That means:

- the verifier fork block must default to the claim snapshot block
- caller-supplied challenge evidence must not be allowed to silently move the
  evaluation to a different block
- if a challenge bundle includes a `pinned_block_number`, it must equal the
  claim snapshot block or be rejected

Plain proof-URI challenges remain manual or advisory, but any deterministic or
executable resolution path must be snapshot-consistent with the original claim.

## Post-Snapshot Changes

Changes after the claim snapshot should be treated as out of scope for that
claim.

Examples:

- proxy implementation upgraded after audit start
- target initialized after audit start
- privileged configuration changed after audit start

These should usually require a new audit rather than being adjudicated as if the
original claim covered the new state.

## Proxy Policy

For proxies, address pinning alone is insufficient.

Minimum expectation:

- detect common proxy patterns that the product claims to support
- resolve implementation identity at snapshot time
- persist both proxy and implementation identity

Current V1 support:

- supports EIP-1967 implementation-slot proxies, which covers the common
  Transparent/UUPS-style layout
- persists:
  - `proxy_kind`
  - `implementation_address_at_snapshot`
  - `implementation_code_hash_at_snapshot`
- explicitly marks EIP-1967 beacon proxies as unsupported in v1 instead of
  pretending they are strongly pinned

If proxy resolution is unsupported or ambiguous:

- surface that clearly in the audit record
- do not represent the claim as strongly snapshot-pinned

## Suggested Rollout

### Phase 1: Snapshot-bound claims

- persist `snapshot_block_number`
- persist `snapshot_block_hash`
- persist target `code_hash`
- show snapshot metadata in audit records and publish metadata
- define published claims as snapshot-bound

### Phase 2: Snapshot-bound executable challenges

- require executable challenge forks to use the claim snapshot block
- reject conflicting `pinned_block_number` values
- record snapshot-consistent execution metadata in challenge dossiers

### Phase 3: Proxy-aware target identity

- resolve supported proxy implementation identity at snapshot time
- persist implementation metadata alongside proxy metadata
- reject or warn on unsupported proxy topologies

## Acceptance-Level Invariants

The system should eventually guarantee:

1. the same published claim can be replayed against the same chain snapshot
2. executable challenges cannot silently switch to a different block context
3. post-snapshot upgrades do not retroactively redefine the audited target
4. proxy targets are either pinned to implementation identity or explicitly
   marked as weakly identified

## Why This Matters

This is not just a verifier convenience. It is part of the meaning of the
economic claim.

If the system does not pin chain state and target identity, then challenge and
resolution logic can end up evaluating a different contract than the one the
auditor actually reviewed.
