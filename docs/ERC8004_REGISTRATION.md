# ERC-8004 Registration Alignment

This note documents the current ERC-8004 alignment for the Proof-of-Audit auditor service.

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
- API path templates
- network context
- capability metadata used by the local workbench

## Current alignment level

Strongest alignment:

- agent identity document shape
- service discovery metadata
- supported trust model declaration

Partial alignment:

- validation story, through stake-backed publication and challenge resolution

Not yet implemented:

- on-chain ERC-8004 identity registration
- validation registry bridge
- reputation registry integration

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
2. register the auditor identity through an ERC-8004-style on-chain registry
3. bridge published audit outcomes into a validation-oriented registry flow
