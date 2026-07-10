# Vision — Proof-of-Audit (v2, July 2026)

> **Proof-of-Audit is the accountability layer that makes machine-made code judgments
> purchasable.** We don't compete on audit intelligence. We make any audit engine's
> verdict economically bonded, independently challengeable, and objectively settled —
> so that buyers, insurers, and other agents can rely on it.

## The problem, restated for the real world

AI can now review smart contracts cheaply and continuously — but nobody can *rely*
on the output. AI audit tools have zero accountability (Immunefi outright bans
AI-generated reports as spam). Insured, accountable audits exist only at human-audit
prices ($25K–$250K, weeks of lead time). The market has an empty quadrant:
**cheap AND bonded**. Meanwhile protocols ship upgrades weekly and audit yearly,
insurers price risk off stale PDFs, and a fast-growing agent economy (x402: ~169M
payments in year one; ERC-8004: 100k+ registered agents) produces and consumes code
with no trust layer at all.

## What Proof-of-Audit is

1. **A bonded attestation format.** An audit verdict published on-chain as a
   machine-readable claim: code hash + chain snapshot + findings commitment +
   auditor identity (ERC-8004) + stake at risk + an explicit challenge policy.
2. **A challenge game with objective settlement.** Anyone can post a bond and a
   *reproducible exploit* (a Foundry test against a pinned fork) against a claim.
   Evidence that demonstrably reproduces is near-objective; settlement should need
   a judge only at the margins. The stake moves; reputation records the outcome.
3. **An engine-agnostic network.** Any audit engine — LLM agents, static analyzers,
   human boutiques — can register an identity, stake behind verdicts, and build a
   public, slash-tested track record. Proof-of-Audit is the settlement rail and the
   record of survival, not the auditor.

## What Proof-of-Audit is not

- **Not an AI auditor.** We do not build audit intelligence; we make it accountable.
  The bundled analyzer exists only as a reference/test engine.
- **Not a bounty marketplace first.** Matching buyers to auditors is a later,
  natural extension once bonded verdicts have demand — not the wedge.
- **Not a demo of agent choreography.** Persona agents with fabricated divergence
  are deleted from the story. Multi-auditor means *real third parties*, or nothing.
- **Not "trustless" until it is.** We say precisely what is enforced on-chain
  (escrow, timing, identity, payout math) and what is not (verdict correctness,
  dispute adjudication) at every stage of the decentralization ladder below.

## Core theses

1. **Accountability, not intelligence, is the moat.** Audit engines are being
   commoditized (Almanax, Savant, Sherlock AI, Octane, ChainGPT). None carry
   consequences for being wrong. A public, on-chain record of *survived challenges*
   is the one credential that can't be prompted into existence — and it compounds.
2. **Reproducible exploits are the only scalable judge.** Open jury adjudication of
   subtle technical claims fails (UMA retreated to whitelisted proposers). A PoC
   that executes against a pinned fork is near-objective evidence. The settlement
   design should maximize the share of disputes resolvable by execution, and
   abstain to humans only for the remainder.
3. **Stake must be sized by pooling, not by the agent's wallet.** A $25 stake on a
   $50M-TVL protocol is theater. Meaningful coverage comes from third parties
   staking behind auditors for yield (the Sherlock precedent, decentralized) —
   which also creates the protocol's revenue line.
4. **The agent economy is the growth story, not the first revenue.** ERC-8004 +
   x402 rails are real and Base-centric, but current per-transaction value is tiny.
   First revenue comes from humans with budgets (protocol teams, insurers);
   agent-to-agent audit trust is the second act we're uniquely positioned for.

## The decentralization ladder (trust-model north star)

We progress adjudication authority in explicit, published stages — never claiming
a rung we haven't reached:

| Stage | Who decides disputes | Status |
| --- | --- | --- |
| 0 | Single arbiter EOA, undisclosed rubric | **Today (must be disclosed)** |
| 1 | Multisig arbiter + published adjudication rubric + full dossier transparency | Near-term |
| 2 | **Binding execution-based settlement** for a narrow claim class (evidence reproduces + target invariant violated ⇒ auto-slash), humans only for abstentions | The core product milestone |
| 3 | Optimistic escalation game (UMA/Kleros-style) or restaked adjudication for the residual human layer | Later |
| 4 | Execution integrity attested (TEE / EigenCompute) so even the operator can't bias the runner | Later |

## Product pillars

1. **Attest** — the bonded verdict primitive, mirrored into the ERC-8004 Validation
   Registry so any wallet, launchpad, or agent can read it.
2. **Challenge** — the exploit-evidence pipeline (already the strongest code asset)
   graduated from advisory to binding for objective cases.
3. **Reputation** — slash-tested track records, portable via ERC-8004; the
   Immunefi-ban counter-artifact.
4. **Coverage** — staking pools that scale a verdict's bond to the value at risk,
   and the fee engine of the business.

## Where this goes

A protocol team merges an upgrade; within minutes a bonded verdict lands on the
diff, priced in dollars not tens of thousands, and their insurer reads it
on-chain and adjusts cover automatically. A security researcher earns more
slashing a wrong verdict than the auditor earned issuing it — so verdicts are
issued carefully. An autonomous agent about to move treasury funds through an
unknown contract pays a few cents via x402 for the contract's bonded audit status
and gets an answer another agent staked real money on. That is trust
infrastructure for machine-made code judgments — the original hackathon insight,
kept; the theater around it, removed.
