# ERC-8004 Registration Alignment

This note documents the current ERC-8004 alignment for the Proof-of-Audit auditor service.

For the exact public claim language and the full identity-versus-settlement boundary, see:

- `/home/koita/dev/hackatons/proof-of-audit/docs/ERC8004_ALIGNMENT.md`

## Scope

The current implementation aligns the auditor registration document and discovery API with the identity and discovery concepts in ERC-8004.

It does not yet claim full protocol compliance.

The current goal is narrower:

- publish an ERC-8004-shaped registration document
- expose that document through a stable API path
- keep project-specific audit metadata in an explicit extension block

## Implemented pieces

### Registration document

The auditor registration document lives at:

- `GET /auditor/registration`

The stable published copy lives at:

- `/home/koita/dev/hackatons/proof-of-audit/docs/registrations/proof-of-audit-auditor.json`

The default canonical URI is:

- `https://raw.githubusercontent.com/akoita/proof-of-audit/main/docs/registrations/proof-of-audit-auditor.json`

The document follows an ERC-8004-shaped structure with these top-level fields:

- `type`
- `name`
- `description`
- `image`
- `services`
- `x402Support`
- `active`
- `registrations`
- `supportedTrust`

This shape is backed by:

- `/home/koita/dev/hackatons/proof-of-audit/agent/proof_of_audit_agent/auditor_manifest.json`

The source manifest is the editable source of truth. The published registration file is generated from that source manifest during release or deploy flows.

### Project extension block

Proof-of-Audit keeps audit-service-specific metadata in:

- `x-proof-of-audit`

Current extension fields:

- `id`
- `version`
- `serviceType`
- `capabilities`
- `operator`
- `resolutionPolicy`

This keeps the standards-oriented registration document clean while preserving the domain details needed by the workbench and API.

### Service discovery record

The discoverable service record remains available at:

- `GET /auditor`

That endpoint is intentionally more operational than the registration document. It includes:

- manifest hash
- canonical registration URI
- API path templates
- network context
- capability metadata used by the local workbench

## Current registration alignment level

Strongest alignment:

- agent identity document shape
- service discovery metadata
- supported trust model declaration

Partial alignment:

- validation story, through stake-backed publication and challenge resolution

Implemented after the validation bridge step:

- canonical validation registry metadata in the API and service record
- request and response documents exposed at `/audits/{id}/validation/request` and `/audits/{id}/validation/response`
- a bridged validation trail that mirrors published claims and resolved outcomes into an ERC-8004-style validation flow

Not yet implemented:

- reputation registry integration

Implemented after the stable publication step:

- canonical registration through the official ERC-8004 Base Sepolia `IdentityRegistry`
- project-local `AgentIdentityRegistry` kept only as a localhost and fallback path
- auditor identity registration that points at the published registration document

## Canonical versus fallback paths

The canonical public identity path is now:

- Base Sepolia official ERC-8004 `IdentityRegistry`
- the recorded auditor `agentId` in `deployments/base-sepolia.json`
- the published registration file in `docs/registrations/proof-of-audit-auditor.json`

The project-local `AgentIdentityRegistry` is no longer part of the public standards story.

It remains only for:

- localhost and Anvil development
- tests that need a self-contained on-chain identity registry
- fallback environments where no official ERC-8004 deployment is available

## Recommended wording

Use:

- `ERC-8004-aligned registration document`
- `ERC-8004-shaped service discovery`

Do not use yet:

- `fully ERC-8004 compliant`
- `complete ERC-8004 implementation`

## Next steps

The remaining planned steps are:

1. publish a stable hosted registration document URI
2. register the auditor identity through the official ERC-8004 on-chain registry when available for the target chain
3. bridge published audit outcomes into a validation-oriented registry flow

## Native versus bridged truth

The authoritative settlement flow remains the native `ProofOfAudit` contract:

- publish
- challenge
- resolve

The ERC-8004 validation path is a mirrored trail for interoperability:

- a published claim opens a validation request
- a resolved outcome submits a validation response
- the bridge does not replace the stake, challenge, or payout logic

This keeps the standards story honest: Proof-of-Audit uses ERC-8004-style identity and validation artifacts without pretending the generic registry is the domain-specific settlement contract.
