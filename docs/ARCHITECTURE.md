# Architecture

The maintained current system view is [Architecture overview](architecture/overview.md). This stable path remains for existing repository links.

Proof-of-Audit uses an API-mediated transaction path: the auditor worker prepares a report, while the API transaction client signs publication and challenge transactions. Challenge verifier output is advisory; the operator-controlled arbiter retains settlement authority, and the `ProofOfAudit` contract permits only its configured arbiter address to resolve a challenge.

For cross-domain implementation details, see [Technical Documentation](TECHNICAL_DOCUMENTATION.md). For deployment status and known source/deployment differences, see [State of the project](strategy/STATE_OF_THE_PROJECT.md).
