# Formal verification (Halmos)

Symbolic property tests for the `ProofOfAudit` escrow, complementing the
Foundry unit, fuzz, and invariant suites. Where fuzzing samples inputs, Halmos
executes the contract over *symbolic* inputs and asks an SMT solver to prove
that a property holds for **every** value — or produces a concrete
counterexample.

- Spec: [`contracts/test/formal/ProofOfAudit.formal.t.sol`](../contracts/test/formal/ProofOfAudit.formal.t.sol)
- Contract under test: `contracts/src/ProofOfAudit.sol`
- Tracking issue: [#314](https://github.com/) (author Halmos symbolic property tests)

## What's covered

Eight universally-quantified properties (`check_` functions) pin the escrow's
core value-conservation and access-control money flows:

| Property | Guarantee |
| --- | --- |
| `check_publishEscrowsExactStake` | Publishing escrows exactly `requiredStake`; any other `msg.value` (below 1 ether) reverts. |
| `check_selfChallengeAlwaysReverts` | An auditor can never challenge their own audit, for any evidence hash. |
| `check_nonAuditorChallengeSucceedsInsideWindow` | A non-auditor challenge with the exact bond succeeds anywhere inside the window and escrows exactly the bond. |
| `check_challengeAfterWindowAlwaysReverts` | Any challenge strictly after the challenge window reverts. |
| `check_resolveMovesExactlyStakePlusBond` | Resolving moves exactly `stake + bond` to the winner (challenger if upheld, else auditor); the direct flow charges no resolution fee. |
| `check_releaseStakeReturnsExactStake` | Releasing an unchallenged audit after the window pays the auditor exactly the stake. |
| `check_expiryNeutrallyUnwinds` | Expiring an unresolved claim challenge returns the claim to `Submitted`, credits the bond as a pull-refund, and leaves the escrow balance unchanged. |
| `check_withdrawExpiredBondPaysExactBond` | After expiry, the challenger withdraws exactly the bond and the refund credit is zeroed. |

## Version

Pinned to **halmos 0.3.3**.

```bash
pip install halmos==0.3.3
```

The suite depends on the `halmos-cheatcodes` submodule at
`contracts/lib/halmos-cheatcodes` (remapped as
`halmos-cheatcodes/=lib/halmos-cheatcodes/src/`).

## Running

```bash
# From the repo root, via the Makefile target:
make test-formal

# Or directly:
PYENV_VERSION=proof-of-audit-3.12 pyenv exec halmos \
  --root contracts --contract ProofOfAuditFormalTest
```

Each property discharges in well under a second; the full suite runs in a
couple of seconds.

## Limitations

- **No `vm.expectRevert`.** Halmos 0.3.x does not support `vm.expectRevert`, so
  "must always revert" properties use a low-level `.call` and assert `!ok`.
- **Bounded symbolic ranges.** Time deltas and values are constrained with
  `vm.assume` so the solver terminates quickly; loops are kept to single-claim
  flows to avoid unbounded unrolling.
- **Scope.** This suite pins the escrow's stake/bond money flows a symbolic
  solver can discharge fast. Heavier protocol-wide rules — multi-claim bounty
  distribution and fee conservation across the full settlement lifecycle — are
  deferred to the Certora spec tracked in
  [#316](https://github.com/). Mutation testing (Gambit) is tracked in
  [#315](https://github.com/).
