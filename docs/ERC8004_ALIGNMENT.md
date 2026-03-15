# ERC-8004 Alignment

This note documents the exact ERC-8004 alignment level for Proof-of-Audit.

The short version:

- Proof-of-Audit uses the official ERC-8004 Base Sepolia identity path for the public auditor agent.
- Proof-of-Audit publishes an ERC-8004-aligned registration document and discovery record.
- Proof-of-Audit mirrors published claims and resolved outcomes into an ERC-8004-aligned validation trail.
- Proof-of-Audit keeps native stake, challenge, and payout logic in the `ProofOfAudit` contract.

It is accurate to call the current system:

- `ERC-8004-aligned`
- `ERC-8004-integrated for identity and validation artifacts`
- `an ERC-8004-backed auditor service with native domain settlement`

It is not accurate to call the current system:

- `fully ERC-8004 compliant`
- `a complete ERC-8004 implementation`
- `an ERC-8004 replacement for audit settlement`

## Exact mapping

| ERC-8004 concept | Proof-of-Audit implementation | Current level |
| --- | --- | --- |
| Identity Registry | Official Base Sepolia `IdentityRegistry` with recorded auditor `agentId` | Strong |
| Registration document | Published auditor registration JSON plus `GET /auditor/registration` | Strong |
| Service discovery | `GET /auditor` operational record and workbench discovery panel | Strong |
| Validation Registry | Official Base Sepolia validation registry metadata plus mirrored request/response documents | Partial-strong |
| Reputation Registry | Not integrated yet | Not implemented |
| Generic settlement logic | Native `ProofOfAudit` contract, not ERC-8004 | Out of scope by design |

## Identity alignment

Canonical public identity path:

- official Base Sepolia `IdentityRegistry`
- recorded auditor `agentId` in `/home/koita/dev/hackatons/proof-of-audit/deployments/base-sepolia.json`
- published registration document in `/home/koita/dev/hackatons/proof-of-audit/docs/registrations/proof-of-audit-auditor.json`

Fallback identity path:

- project-local `AgentIdentityRegistry`
- used only for localhost, Anvil, and self-contained tests

This means the public story should always lead with the official ERC-8004 registry, and only mention the local registry as a development fallback.

## Validation alignment

Proof-of-Audit mirrors lifecycle events into validation artifacts:

- when an audit is published, the API emits an ERC-8004-aligned validation request
- when the outcome is resolved, the API emits an ERC-8004-aligned validation response

Those artifacts are accessible at:

- `GET /audits/{id}/validation/request`
- `GET /audits/{id}/validation/response`

The validation trail is standards-oriented interoperability data. It is not the source of truth for funds or dispute settlement.

## Native settlement remains canonical

The authoritative settlement system is still the native `ProofOfAudit` contract:

- publish claim
- escrow stake
- open challenge
- resolve challenge
- pay out the winner

That contract is the domain-specific enforcement layer. ERC-8004 is used here for:

- identity
- registration
- discoverability
- validation interoperability

This is the most important line to keep clear in demos and reviews:

> ERC-8004 identifies the auditor and mirrors the validation trail, while `ProofOfAudit` remains the native settlement contract for stake, challenge, and payout logic.

## Reviewer-safe wording

Recommended short wording:

> Proof-of-Audit is an ERC-8004-aligned auditor service. The auditor uses the official Base Sepolia identity registry, publishes a standards-shaped registration document, and mirrors validation artifacts, while the native `ProofOfAudit` contract remains the settlement layer for stake, challenge, and resolution.

Recommended one-line submission wording:

> Proof-of-Audit gives a named auditor agent an official ERC-8004 identity and validation trail, then lets it stake behind a code judgment that can be challenged and resolved on-chain.

Recommended demo wording:

> The ERC-8004 pieces identify the agent and make its validation trail portable. The domain-specific contract still handles the money, dispute, and enforcement logic.

## Claims to avoid

Avoid these statements unless the implementation changes materially:

- `Proof-of-Audit fully implements ERC-8004`
- `ERC-8004 handles our full audit settlement flow`
- `Proof-of-Audit replaces the need for domain-specific contracts`
- `The validation registry is the settlement source of truth`

## Related docs

- `/home/koita/dev/hackatons/proof-of-audit/docs/ERC8004_REGISTRATION.md`
- `/home/koita/dev/hackatons/proof-of-audit/docs/ARCHITECTURE.md`
- `/home/koita/dev/hackatons/proof-of-audit/docs/DEMO_SCRIPT.md`
- `/home/koita/dev/hackatons/proof-of-audit/docs/AGENT_API.md`
