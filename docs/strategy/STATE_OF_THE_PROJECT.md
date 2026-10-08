# State of the project

Reviewed on 7 October 2026 against `main` at
`08766b1a2102938b47f8e1d1febf6a06dd2ca394`. This is a current inventory of repository
behavior and recorded evidence, not a security certification or an independent
reverification of public-chain state. The [roadmap](./ROADMAP.md) remains the
adopted delivery plan; Phase 0 has not exited.

**Release update, 8 October 2026:** current source was deployed to Base Sepolia
at `0x10eb28034c2b8f77400c3c2eaa1984b019655ae6`. Its creation and runtime bytecode
match source commit `c7c2544`. BaseScan source verification is complete after
recovering from a registration-generation failure; see the [current deployment record](../DEPLOYMENT.md#current-status).
The inventory below retains the 7 October review evidence. A live settlement
cycle and the other Phase 0 gaps remain outstanding.

## Implemented in source

| Capability | Evidence and boundary |
| --- | --- |
| Stake, challenge, resolution and payout | [ProofOfAudit](../../contracts/src/ProofOfAudit.sol) and [contract tests](../../contracts/test/ProofOfAudit.t.sol); the arbiter supplies the dispute verdict. |
| Request escrow, claim accounting and fees | Implemented in the same contract; availability depends on the deployed version. |
| Contract hardening | Source rejects direct self-challenges and invalid constructor parameters, includes request-claim challenge expiry, and has [fuzz/invariant coverage](../../contracts/test/ProofOfAuditInvariant.t.sol). |
| Audit submissions and persistence | [AuditService](../../api/proof_of_audit_api/service.py), [store implementations](../../api/proof_of_audit_api/store.py), and [service tests](../../api/tests/test_service.py); audit-request persistence remains separate JSON. |
| Source and chain provenance | [Snapshot semantics](../AUDIT_SNAPSHOT_SEMANTICS.md) and [executable evidence format](../EXECUTABLE_EVIDENCE_BUNDLE.md). Provenance does not prove report correctness. |
| Evidence review | Integrity/execution checks, semantic comparison and structured dossiers; current executable verification stays advisory. See [verifier design status](../CHALLENGE_VERIFIER_V2.md). |
| Identity and lifecycle mirrors | ERC-8004-aligned [registration](../ERC8004_REGISTRATION.md), validation artifacts and configurable reputation integration. Mirror availability depends on compatible configured registries. |
| API baseline protection | [API-key guard and per-process rate limiter](../../api/proof_of_audit_api/security.py), CORS configuration, and [security tests](../../api/tests/test_security.py). This is not customer/operator role separation. |
| Signing-role checks | [Configuration](../../api/proof_of_audit_api/config.py) and API startup reject shared trust-role keys on non-local networks. Local development permits shared test keys. |
| Verification and hooks | Python, contract, browser and system test layers; [Halmos properties](../FORMAL_TESTING.md); [pre-commit security gate](../SECURITY_AUDIT_WORKFLOW.md). |

The [CI run on this baseline](https://github.com/akoita/proof-of-audit/actions/runs/37621817505)
passes its five jobs. The preceding local validation recorded 328 Python tests
passing with six live-testnet skips, 63 contract tests passing, and eight Halmos
checks passing. The executable-evidence resolver module was excluded under the
repository test instructions. These are dated observations, not permanent test
counts or evidence of a working public deployment.

## Fixture and live execution

The default `deterministic` demo returns prewritten benchmark reports.
[The worker](../../agent/proof_of_audit_agent/worker.py) can filter fixture
findings by persona detector scope; this does not represent independent
researchers disagreeing about a contract. Persona showcase work remains parked.

The bundled live analyzer has three regex detector families and is a reference
implementation, not a comprehensive audit engine. Hosted engine integration
requires an available, configured service; the repository's client contract
alone does not prove that service is operating. The current deployed-address
submission path validates live execution and rejects unsupported execution
rather than treating a fixture fallback as a successful live audit.

The [verifier benchmark](../../agent/proof_of_audit_agent/verifier_benchmark.py)
has six replay cases with predefined runner/extractor results. It checks policy
classification regressions, not actual exploit execution reliability or
real-world audit accuracy.

## Source versus recorded deployment

At the 7 October review, the Base Sepolia manifest recorded the
legacy four-argument deployment at
`0xf2da3947d028b85e597fe1df4633a87ef4a85f24`. It does not establish deployment of
the current request/fee subsystem or later hardening. No newer deployment was
verified in this review. Source-level guarantees must not be attributed to the
recorded address without matching release and bytecode evidence. The manifest
has since been updated for the 8 October release described above.

[Issue #303](https://github.com/akoita/proof-of-audit/issues/303) tracks redeploying
or disclosing the divergence. [PR #323](https://github.com/akoita/proof-of-audit/pull/323)
proposes disclosure and remained open at review. Its existence is not evidence
that the disclosure has landed or that the contract was redeployed. PR #323 was
subsequently closed in favor of the redeployment decision on #303.

The [22 March smoke record](../proofs/base-sepolia-smoke-2026-03-22.md) contains
skipped live tests. [Issue #293](https://github.com/akoita/proof-of-audit/issues/293)
still tracks a real publish → challenge → resolve → payout record. A local
end-to-end run or a green skipped smoke run does not satisfy that requirement.
See [deployment](../DEPLOYMENT.md) for procedures.

## Remaining readiness gaps

Manual resolution is backed by the operator's arbiter key. Submission and
resolution currently share the generic mutating API guard; API keys are not
scoped into customer and arbiter roles. The frontend helper has no credential
integration for protected requests. Treat these as limitations before sharing
an operated instance with customers, not as implemented authorization controls.

Audit-request persistence rewrites a whole JSON catalogue and can lose concurrent
updates. [Issue #300](https://github.com/akoita/proof-of-audit/issues/300) tracks
migration into the transactional store layer. Execution occurs before a draft
record is persisted; durable jobs, restart recovery and transaction reconciliation
remain work to evaluate before a hosted pilot.

The worker temporarily mutates a shared backend for runtime overrides. Concurrent
submissions need isolated per-job execution and a concurrency check. The UI also
maps confidence labels to uncalibrated numeric security scores; these should not
be interpreted as a measurement of contract safety.

The arbiter, runner and RPC remain trusted boundaries. Binding objective
settlement, meaningful coverage, independent engine demand, and commercial pilot
value have not been established. See the [decentralization ladder](./VISION.md#the-decentralization-ladder-trust-model-north-star)
and [backlog snapshot](./BACKLOG_TRIAGE.md).

## Documentation and proposed direction

The [documentation map](../README.md) separates current system descriptions,
reference, operational guidance, proposals, and history. Hackathon packaging is
[archived](../archive/hackathon-2026/README.md). Earlier claims that the API had no
protection, contract source had no invariant tests, or hook bypassing was policy
are superseded by the implemented work above.

The October review proposes a narrower pilot workflow and earlier demand
validation in [release and pilot focus](../design/release-and-pilot-focus.md).
That document is a draft. Its suggested sequencing and gates have not replaced
[Roadmap v2](./ROADMAP.md).
