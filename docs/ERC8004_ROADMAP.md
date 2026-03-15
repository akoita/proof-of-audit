# ERC-8004 Roadmap Status

This note records the ERC-8004 integration plan as it exists in the repository today.

Use it as the roadmap/status companion to:

- [/home/koita/dev/hackatons/proof-of-audit/docs/ERC8004_ALIGNMENT.md](/home/koita/dev/hackatons/proof-of-audit/docs/ERC8004_ALIGNMENT.md)
- [/home/koita/dev/hackatons/proof-of-audit/docs/ERC8004_REGISTRATION.md](/home/koita/dev/hackatons/proof-of-audit/docs/ERC8004_REGISTRATION.md)

## Status snapshot

Current public position:

- official ERC-8004 Base Sepolia `IdentityRegistry` is the canonical auditor identity path
- Proof-of-Audit publishes a stable ERC-8004-aligned registration document
- the API exposes a discoverable service record plus registration and validation artifacts
- native stake, challenge, and payout logic still live in `ProofOfAudit`

That means the ERC-8004 work is no longer just planned. The main identity and validation bridge steps are already implemented.

## Completed roadmap items

### 1. Registration document alignment

Status: complete

Implemented:

- source manifest in `/home/koita/dev/hackatons/proof-of-audit/agent/proof_of_audit_agent/auditor_manifest.json`
- stable published registration file in `/home/koita/dev/hackatons/proof-of-audit/docs/registrations/proof-of-audit-auditor.json`
- API surfaces:
  - `GET /auditor`
  - `GET /auditor/registration`
  - `GET /config`

Result:

- the auditor now reads as an ERC-8004-aligned service, not just a project-local profile

### 2. Stable publication path

Status: complete

Implemented:

- generated published registration artifact during release/deploy flows
- canonical registration URI recorded in release metadata
- public registration copy checked into the repo for discoverability

Result:

- the auditor identity points to a stable, reviewable registration document

### 3. Official on-chain identity registration

Status: complete

Implemented:

- official Base Sepolia `IdentityRegistry` is now the canonical public registry
- recorded auditor `agentId` and registry address in `/home/koita/dev/hackatons/proof-of-audit/deployments/base-sepolia.json`
- localhost keeps the custom `AgentIdentityRegistry` only as a development fallback

Result:

- the public story uses the official ERC-8004 identity path instead of a parallel custom registry

### 4. Validation bridge

Status: complete

Implemented:

- ERC-8004-aligned validation request/response documents for published and resolved audits
- validation registry metadata exposed through the API and workbench
- native settlement preserved in `ProofOfAudit`

Result:

- claims and outcomes now have a portable validation trail without pretending the registry is the settlement engine

## Remaining optional work

These are now follow-on enhancements, not blockers for the current standards story.

### Reputation registry integration

Status: not implemented

Possible future scope:

- mirror challenge outcomes into an ERC-8004 reputation-oriented trail
- derive auditor-level performance summaries from resolved audits

This is the largest remaining standards gap.

### Additional chain registrations

Status: not started

Possible future scope:

- register the auditor on more than one chain when official ERC-8004 deployments exist and match the product story

### Multi-agent discovery and purchase path

Status: partially prepared, not productized

Current state:

- the service is discoverable
- the registration document is public
- the API is agent-facing

Still missing for a stronger marketplace-style story:

- external buyer flow
- paid discovery/purchase loop
- broader service negotiation semantics

## What should stay unchanged

The roadmap should not drift into claiming that ERC-8004 replaces the native contract.

Keep these boundaries:

- `ProofOfAudit` remains the source of truth for stake, challenge, resolution, and payout
- ERC-8004 handles identity, discovery, and validation interoperability
- localhost fallback infrastructure is for development, not the public standards narrative

## Honest summary

The planned ERC-8004 roadmap is mostly complete for the current scope.

What remains is refinement and optional breadth:

- reputation
- more chains
- deeper multi-agent service flows

The current repo already supports the honest public claim:

> Proof-of-Audit is an ERC-8004-aligned auditor service with official public identity and a mirrored validation trail, while the native `ProofOfAudit` contract remains the settlement layer.
