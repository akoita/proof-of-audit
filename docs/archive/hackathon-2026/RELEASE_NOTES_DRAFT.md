# Release Notes Draft

## Proof-of-Audit Public Alpha

Proof-of-Audit is trust and enforcement infrastructure for agent-made code judgments. This public alpha demonstrates how a named auditor agent can publish a claim on-chain, stake behind it, and face transparent challenge and resolution when that claim is disputed.

## Highlights

- named auditor identity with a stable service manifest
- discoverable auditor service record via API
- real publish and challenge transactions against `ProofOfAudit`
- deterministic challenge verification for curated benchmark cases
- fallback governance path for ambiguous evidence
- local Anvil workflow with deployable demo fixtures
- live Base Sepolia deployment and verification
- system-level and browser-level end-to-end coverage

## Current scope

This alpha is intentionally narrow:

- one named auditor service
- one compact on-chain claim registry
- a deterministic benchmark-backed review worker
- one challenge type and one payout path
- local demo fixtures plus Base Sepolia deployment support

## What this release is not

- not a general-purpose smart contract audit platform
- not a full autonomous arbitration system
- not a marketplace for many agent services

## Best current use

This release is best used as:

- a demo of accountable agent judgments
- a reference implementation for stake-backed claim publication
- a small foundation for agent trust and dispute infrastructure

## Recommended reviewer path

1. read `/home/koita/dev/hackatons/proof-of-audit/README.md`
2. follow `/home/koita/dev/hackatons/proof-of-audit/docs/DEMO_SCRIPT.md`
3. inspect `/home/koita/dev/hackatons/proof-of-audit/docs/ARCHITECTURE.md`
4. run the local flow from `/home/koita/dev/hackatons/proof-of-audit/docs/DEPLOYMENT.md`
