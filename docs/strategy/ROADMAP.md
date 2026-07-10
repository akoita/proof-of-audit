# Roadmap v2 — From Hackathon Prototype to Real Product (July 2026)

Supersedes the hackathon-era `docs/ROADMAP.md` phases (which are delivery history).
Each phase has an exit criterion; do not start the next phase's headline work
before the previous exit criterion is met. Rationale in
[PRODUCT_STRATEGY.md](./PRODUCT_STRATEGY.md); current-state inventory in
[STATE_OF_THE_PROJECT.md](./STATE_OF_THE_PROJECT.md).

## Phase 0 — Truth & hygiene (weeks, not months)

Make every public claim true before making new claims.

- Rewrite README/pitch language: disclose single-arbiter adjudication, advisory
  verifier status, and the deterministic demo mode plainly; remove "not a
  platform's discretion" phrasing until ladder stage 2.
- Fix stale docs: `ARCHITECTURE.md` and `AGENT_INTERACTION_FLOW.md` still describe
  the retired benchmark-lookup auto-resolution; reconcile with
  `TECHNICAL_DOCUMENTATION.md`. Archive judge/submission-era docs to `docs/archive/`.
- **Record a real Base Sepolia publish→challenge→resolve cycle** with tx links,
  replacing the "green no-op" smoke evidence.
- Contract truth: the deployed contract predates the bounty/fee subsystem. Either
  deploy the current source (after Phase-0 fixes below) or clearly mark the
  marketplace surface as undeployed.
- Contract fixes before any redeploy: block self-challenge in the direct flow;
  validate arbiter ≠ 0; add a settlement-timeout path so one unresolved challenge
  cannot freeze a request's escrow forever; add fuzz/invariant tests.
- Key separation: arbiter, auditor-owner, publisher, validator, and
  reputation-operator keys must never fall back to one env key. Fail loud instead.
- API hardening baseline: API-key auth on mutating endpoints, rate limits, CORS
  allowlist, move audit-request storage off the flat JSON file.
- Fix the pre-commit security hook so `--no-verify` stops being standard practice.

**Exit criterion:** an outside security engineer can read the repo and find no gap
between claims and code.

## Phase 1 — A real audit engine and the first bonded verdicts

We don't build intelligence; we plug it in.

- Promote the pluggable-auditor contract (service HTTP contract + report schema,
  already specced) to the primary integration surface; the bundled static analyzer
  becomes a reference engine for tests only.
- Integrate **one real engine** end-to-end (own agent-forge LLM service, an OSS
  analyzer like Slither+LLM triage, or a partner AI-audit tool) and publish its
  **EVMbench** results.
- Ship the **bonded diff-audit pipeline**: GitHub App / CI action → engine run →
  bonded verdict on the diff (code hash + snapshot pinning already exists) →
  ERC-8004 validation mirror.
- Delete the fabricated multi-agent divergence path (`_apply_detector_scope`
  personas); keep the multi-service registry only as the third-party onboarding
  surface it was meant to be.
- Land 1–3 design-partner protocols on free/cheap pilots.

**Exit criterion:** ≥ 10 bonded verdicts on real (non-fixture) code from a real
engine, at least one produced by a design partner's CI.

## Phase 2 — Objective settlement (the core product milestone)

Graduate the exploit-evidence pipeline from advisory to binding.

- Define the **binding claim class**: evidence bundle hash-committed on-chain +
  reproduces on pinned fork + violates a machine-checkable invariant from the
  published claim ⇒ automatic slash, no human in the loop. Everything else abstains.
- Arbiter EOA → **multisig + published adjudication rubric** + public dossiers for
  every abstention ruling (ladder stage 1→2).
- Launch the **challenge bounty program**: seed rewards for slashing wrong verdicts;
  open-source a claim-scanner so contest hunters can hunt our ledger.
- Grow the verifier benchmark corpus from 6 cases to a real eval set; publish
  verifier precision/abstention metrics.
- Public challenge-outcome ledger page (the Immunefi-ban counter-artifact).

**Exit criterion:** a majority of settled challenges resolve by execution, not by
the arbiter, and at least one wrong verdict has been genuinely slashed.

## Phase 3 — Coverage and first serious revenue

Make the stake mean something and charge for it.

- **Coverage pools**: third parties stake behind an auditor's verdicts for yield;
  verdict-level coverage scales with pool depth; protocol fee on distribution
  (re-use the written-but-undeployed fee engine, redeployed honestly).
- Insurance pilot: expose the bonded-verdict feed to an underwriter
  (Nexus/OpenCover ecosystem) as an underwriting input; paid data pilot.
- Mainnet/Base mainnet deployment of the settlement contract after external review
  of `ProofOfAudit.sol` (eat the dog food: publish a bonded verdict on ourselves).
- Pricing: per-diff fees + coverage riders; ERC-20/USDC bounty support.

**Exit criterion:** first recurring revenue (diff-audit subscriptions or
underwriter data pilot) and ≥ $100K aggregate coverage staked.

## Phase 4 — The agent economy act

Now the hackathon's multi-agent story becomes real.

- **x402-priced attestation API**: agents pay cents to read (or commission) bonded
  audit status before interacting with a contract; listing in agent app stores /
  Virtuals ACP.
- Third-party auditor network: open onboarding of engines with ERC-8004 identities,
  per-engine slash-tested leaderboards (the honest version of the multi-agent
  dashboard already built).
- ERC-8004 Reputation Registry integration (the acknowledged largest standards gap)
  once the spec stabilizes; cross-chain settlement if demand exists.
- Optimistic escalation (UMA/Kleros-style) or restaked adjudication for the
  residual human layer; evaluate EigenCompute for runner integrity (ladder 3–4).

**Exit criterion:** agent-initiated (not human-initiated) paid attestation volume.

## Explicitly parked (revisit only with evidence)

- Multi-agent persona demos and demo orchestration polish.
- Marketplace UX as a headline surface (bounty forms stay, quietly).
- TEE evidence execution (RFC no-go stands).
- Cross-chain expansion before mainnet traction.
- Building a proprietary frontier audit engine.
