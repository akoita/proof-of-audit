# Product Strategy (July 2026)

Companion to [VISION.md](./VISION.md). Grounded in the market research summarized
below; sources cited inline.

## 1. Market picture

**The audit market's empty quadrant.** Human audits: $5K–$250K+, typical DeFi
engagement $25K–$100K (Sherlock 2026 pricing reference). Contest pools: $100K–$2M+
(Code4rena, Sherlock, Cantina, CodeHawks). AI tools price 10–100x below human
audits but carry **zero accountability** — Immunefi bans AI-generated reports as
spam. Only one established player sells accountability: **Sherlock**, whose audits
carry up to $2M repayment backed by staking pools — at human-audit prices, and its
AI product is uninsured. Nobody sells *cheap and bonded*. That is our quadrant.

**Enabling rails matured in the last 12 months:**
- **ERC-8004** (identity/reputation/validation registries): stable v1 Oct 2025,
  mainnet + Base canonical deployments Jan 2026, 100k+ registered agents across
  12–16 chains, integrations announced by ENS, EigenLayer, The Graph. Caveat: still
  Draft; almost nothing exercises the Validation Registry with real stakes — we can
  be first, but must not depend on spec stability.
- **x402 agent payments**: ~169M payments, 590K buyers in year one; foundation
  includes Google, Visa, AWS, Circle, Anthropic. Counter-signal: mostly sub-dollar
  pings (~$50M total volume) — a distribution channel, not yet a revenue base.
- **EigenCloud/EigenCompute**: verifiable execution with slashing — complementary
  infrastructure (execution integrity), not a competitor (verdict correctness).
- **UMA's lesson**: open adjudication of subtle claims failed; Managed OO V2
  whitelisted proposers. Validates our execution-based settlement thesis.

**Direct competitors doing staked, challengeable AI audit verdicts: none found.**
Biggest fast-follow threat: Sherlock bolting coverage onto Sherlock AI. Our speed
advantage is that we already have the on-chain challenge/settlement rails and
ERC-8004 alignment they'd have to build.

## 2. Ideal customers and wedge sequence

| # | Wedge | Buyer | Why it works | Price shape |
| --- | --- | --- | --- | --- |
| 1 | **Bonded diff-audits (continuous re-audit)** | Protocol teams that audited at launch but ship upgrades weekly | Empty price/accountability quadrant; $500–$5K per diff vs $60K re-audit; CI-native | Per-diff fee + optional coverage rider |
| 2 | **Insurance underwriting signal** | Nexus Mutual / OpenCover-style underwriters (cover only ~0.25% of DeFi TVL today) | They already price exactly the risk our stake represents; machine-readable bonded verdicts are a premium-pricing input | Data/API licensing + settlement fees |
| 3 | **Agent-economy audit trust** | Autonomous agents & agent platforms (Virtuals ACP, x402 ecosystem) | No human audit firm serves machine-speed, machine-priced audit queries at all | x402 micropayments per attestation read/issue |
| 4 | **Pre-listing screening** | Launchpads, long-tail token platforms, wallets | $60K human audit uneconomical; unbonded AI scan worthless; a bonded badge is the middle | Per-listing fee, badge licensing |

Sequence matters: wedge 1 creates the verdict supply and track record; wedge 2
monetizes the track record; wedges 3–4 scale distribution.

## 3. Positioning

- **Say:** "The accountability layer that makes AI audit output purchasable."
  "Slash-tested track records." "Verdicts with consequences."
- **Don't say:** "AI auditor" (crowded, low-trust), "trustless settlement" (untrue
  at stage 0–1 of the decentralization ladder), "replaces audits" (it complements
  launch audits and fills the gaps between them).
- **Credibility artifacts to build, in order:** (1) a recorded, real
  publish→challenge→resolve cycle on Base Sepolia; (2) published EVMbench numbers
  for any engine we bundle or onboard (EVMbench — OpenAI+Paradigm, Feb 2026 — is
  now the yardstick); (3) a public challenge-outcome ledger; (4) a first paying
  diff-audit pilot.

## 4. Business model

1. **Settlement/protocol fees** — the fee engine already written into the
   (undeployed) contract source: bps on bounty distribution and dispute payouts.
   Keep, but re-deploy honestly.
2. **Coverage pool spread** — the Sherlock-proven line: stakers underwrite auditor
   verdicts for yield; protocol takes a spread. This is where stake stops being
   theater and revenue stops being hypothetical.
3. **Attestation reads at machine scale** — x402-priced API for agents/wallets
   reading bonded audit status. Cents per call, high volume, pure margin.
4. **SaaS for the diff-audit pipeline** — GitHub App + CI integration
   subscription for protocol teams.

## 5. What we deliberately do NOT build

- **Our own frontier audit engine.** We integrate engines (open the pluggable
  auditor contract defined in the pluggable-integration docs; recruit existing AI
  audit tools as staking auditors). The bundled static analyzer remains a
  reference implementation for tests.
- **A generalized agent marketplace UI.** The marketplace views built post-hackathon
  are parked until wedge 1–2 revenue exists.
- **Multi-agent demo choreography.** Real third-party auditors or nothing.
- **TEE evidence execution (for now).** The RFC's no-go stands; EigenCompute is the
  cheaper path when execution integrity becomes the binding constraint.

## 6. Risks and honest counters

| Risk | Reality check | Mitigation |
| --- | --- | --- |
| AI engines miss business-logic bugs; stakes will actually get slashed | True — and that's the product working | Coverage pools price this; per-engine track records let the market price engines differently; start with narrow claim classes (diff-scoped) |
| Sherlock copies fastest | Real | Speed on rails we already have; engine-agnostic network vs their closed shop; agent-economy distribution they won't chase first |
| Challenge liquidity (nobody challenges) | Cold-start on the adversarial side | Seed a challenge bounty program (wedge for security researchers currently grinding contests); auto-scan published claims with open tooling |
| ERC-8004 still Draft | Spec churn possible | Keep the alignment layer thin and mirrored (already the design); settlement contract is standard-independent |
| Solo-maintainer bus factor | The repo's actual biggest risk | The roadmap explicitly front-loads: smaller honest scope, partners/co-founder search, external auditor onboarding over feature breadth |
| Regulatory shape of "coverage" | Staked repayment ≈ discretionary mutual cover | Follow Sherlock/Nexus precedent (discretionary, DAO-governed); jurisdiction review before mainnet coverage pools |

## 7. Success metrics (12 months)

- ≥ 1 real third-party audit engine staking behind verdicts on our rails.
- ≥ 3 protocol teams on paid bonded diff-audits; ≥ 50 bonded verdicts published.
- ≥ 10 genuine challenges settled, ≥ 80% via binding execution (not the arbiter).
- 1 insurer/underwriter consuming the verdict feed (paid pilot counts).
- Arbiter authority reduced to abstention-only cases (ladder stage 2).
- Zero marketing claims that the state-of-the-project audit would contradict.
