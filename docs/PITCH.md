# Pitch Script

Use this to open the Synthesis demo. Total airtime: about 30 seconds before switching to the live walkthrough.

## Hook — 5 seconds

> What if the AI agent that said your smart contract was safe had to bet real money on that claim?

## Problem — 10 seconds

> Today, AI agents make code judgments with zero accountability. There's no way to verify the claim, no economic skin in the game, and no recourse when they're wrong. You're trusting a black box.

## Solution — 10 seconds

> Proof-of-Audit makes agent judgments visible, stake-backed, and challengeable. The auditor stakes ETH behind its verdict. Anyone can challenge it with evidence. The escrow settles on-chain under fixed rules; the dispute verdict itself comes from a designated arbiter today — decentralizing that judgment is the roadmap.

## Transition — 5 seconds

> This is live on Base Sepolia right now. Let me show you the full trust loop.

Then walk through the demo:

1. show the auditor identity and ERC-8004 registration
2. submit a contract and show the draft claim
3. publish on-chain — point at the stake amount and tx hash
4. challenge with evidence — show the manual-review path or executable advisory output
5. resolve the challenge and show the final payout and validation trail

## If you only have one sentence

> Proof-of-Audit is trust infrastructure that makes AI agent code judgments stake-backed, challengeable, and transparently enforceable on-chain.

## What not to say

- ❌ "We built an AI smart contract auditor"
- ❌ "We wrapped a static analyzer"
- ❌ "The value is the bug detector itself"

These framings undersell the project. The innovation is **accountability**, not automation.

## What to emphasize

- ✅ Trust comes from visible economic commitment, not branding
- ✅ The agent is identifiable before it makes a claim (ERC-8004)
- ✅ Plain proof-URI evidence goes to manual review; executable evidence gets an advisory verifier verdict
- ✅ Live deployment on Base Sepolia with real transactions
- ✅ This is **infrastructure** — any agent can be plugged in
