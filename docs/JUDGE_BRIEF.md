# Judge Brief

## One sentence

Proof-of-Audit is trust infrastructure for agent-made smart contract judgments: an auditor agent publishes a claim on Base, stakes behind it, and can be challenged with evidence.

## Theme fit

- Primary theme: `Agents that trust`
- Why: the core product is about making agent judgments visible, stake-backed, and challengeable instead of asking users to trust a black box
- Secondary theme: `Agents that cooperate`
- Why: challengers, arbiters, and auditor agents all interact through a shared on-chain process instead of a platform-owned review queue

## Why Ethereum and Base matter

- the audit claim, stake, challenge bond, and resolution all live on-chain
- ERC-8004 registration gives the auditor a discoverable identity before it makes a claim
- Base Sepolia is the live settlement network for the public prototype

## What is live today

- live `ProofOfAudit` settlement contract on Base Sepolia
- live ERC-8004 auditor identity registration on Base Sepolia
- local web and API demo stack for full publish and challenge walkthroughs
- plain proof-URI challenges recorded for manual review
- executable evidence path with an advisory verifier and manual fallback

## What to do first

1. Read the evaluation path in the README.
2. Open the live registration document and Base Sepolia contract.
3. If you want the full product walkthrough, run the local evaluation path.

## Public links

- Repo: https://github.com/akoita/proof-of-audit
- Live contract: https://sepolia.basescan.org/address/0xf2dA3947d028b85e597Fe1Df4633a87eF4A85F24
- ERC-8004 registration document: https://raw.githubusercontent.com/akoita/proof-of-audit/main/docs/registrations/proof-of-audit-auditor.json
- Auditor identity registry: https://sepolia.basescan.org/address/0x8004A818BFB912233c491871b3d84c89A494BD9e
- Validation registry: https://sepolia.basescan.org/address/0x8004B663056A597Dffe9eCcC1965A193B7388713
- Public API/docs: not currently published as a stable public endpoint

## Current limitations

This prototype is strongest as trust and accountability infrastructure, not as a fully autonomous verifier. The settlement contract and ERC-8004 identity path are live on Base Sepolia, but the easiest complete product evaluation path is still local rather than a stable public web/API deployment. Plain proof URIs do not auto-resolve; they are recorded for manual review. Executable evidence produces an advisory verdict, but final resolution can still require an arbiter path.
