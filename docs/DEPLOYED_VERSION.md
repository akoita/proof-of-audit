# Deployed version vs current source

**Canonical truth document for public networks** (issue
[#303](https://github.com/akoita/proof-of-audit/issues/303)).

## Decision (Phase 0 — Truth & hygiene)

Until a full redeploy of the current `contracts/src/ProofOfAudit.sol` is
published and verified, **public Base Sepolia stays on the legacy deployment**.
The marketplace / `AuditRequest` surface is **undeployed on public networks**
and must be treated as source + local/preview only.

Redeploy remains the long-term path (see release pipeline prep and local Anvil
deploys). This document chooses **explicit disclosure** over implying live
parity.

## Live Base Sepolia (`deployments/base-sepolia.json`)

| Field | Value |
| ----- | ----- |
| Network | `base-sepolia` (chain id `84532`) |
| Contract | `ProofOfAudit` |
| Address | `0xf2da3947d028b85e597fe1df4633a87ef4a85f24` |
| Deployment status | `deployed` (Basescan verified) |
| Constructor arity on chain | **4** arguments (arbiter, stake, challenge bond, challenge window) |
| Current source constructor arity | **8** arguments (adds treasury, resolution window, protocol/resolution fee bps) |

### Live on that address

- Legacy single-auditor path: publish → challenge → resolve → release stake
- Fixed stake / challenge-bond / challenge-window parameters recorded in the
  deployment manifest
- ERC-8004 auditor identity registration uses **separate registry addresses**
  documented in the same JSON (not the marketplace request path)

### Not live on that address (source-only / local / API preview)

- `AuditRequest` bounty escrow marketplace
- Request-bound claims (`submitAuditRequestClaim` and related settlement)
- Protocol / resolution fee bps and treasury fee routing from the current
  constructor
- Any UI/API flow that returns an on-chain marketplace `request_id` against the
  public Base Sepolia settlement address

## Source of truth files

| Path | Role |
| ---- | ---- |
| [`deployments/base-sepolia.json`](../deployments/base-sepolia.json) | Live address + feature surface flags |
| [`contracts/src/ProofOfAudit.sol`](../contracts/src/ProofOfAudit.sol) | Current source (8-arg constructor) |
| [`docs/AUDIT_REQUEST_PROTOCOL.md`](./AUDIT_REQUEST_PROTOCOL.md) | Marketplace protocol design (undeployed publicly) |
| [`docs/AGENT_API.md`](./AGENT_API.md) | API surface including marketplace routes |

## Operator guidance

1. Do not advertise the public Base Sepolia address as a live marketplace.
2. Local Anvil deploys (`scripts/deploy-local.sh`) exercise the **current**
   source, including marketplace primitives when present.
3. When a full public redeploy lands: update `deployments/base-sepolia.json`,
   this file, README “What's next”, and Basescan verification in the same PR.

## Acceptance for #303

Deployed bytecode and the documented feature set either match, **or** the
divergence is disclosed everywhere marketplace is mentioned. This document plus
the linked banners implement the disclosure path.
