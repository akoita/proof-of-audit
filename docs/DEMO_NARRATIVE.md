# Demo Narrative

This note keeps the live demo framing consistent across the web app, README, and submission materials.

## Core story

Proof-of-Audit is not mainly a smarter audit engine.

It is infrastructure that makes an agent's code judgment:

- visible
- stake-backed
- challengeable
- enforceable

## 30-second framing

Proof-of-Audit lets a named auditor agent publish a smart contract judgment on Base and stake behind that claim. If the claim is wrong, anyone can challenge it with evidence and the outcome is resolved through a transparent on-chain process instead of a centralized platform.

## 60-second demo arc

1. This is the auditor agent identity, its discoverable service record, and the active chain configuration.
2. I submit a contract and the agent produces a review claim.
3. The agent stakes on that claim and publishes it on-chain.
4. A challenger submits evidence against the claim.
5. The system verifies the challenge path and records the outcome on-chain.

## What to emphasize

- trust comes from visible economic commitment, not branding
- the auditor is surfaced as a named service with a stable manifest hash and discovery path
- cooperation comes from neutral enforcement, not platform discretion
- Base is the chain where the public claim and challenge lifecycle live
- deterministic verification is the fast path; human arbitration is fallback only

## What not to emphasize

- "we built an AI smart contract auditor"
- "we wrapped a static analyzer"
- "the value is the bug detector itself"

Those framings undersell the strongest part of the project.

## Best one-line description

Proof-of-Audit is trust and enforcement infrastructure for agent-made code judgments.
