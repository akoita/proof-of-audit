# Auditor Reputation Model

Proof-of-Audit exposes an explainable reputation summary for each auditor
service. The goal is to describe how that auditor's claims have held up after
challenge, not to hide judgment behind a black-box score.

## Formula

- if there are no resolved challenges, the score is neutral at `50/100`
- otherwise:

`score = round(100 * challenge_rejected_count / resolved_challenge_count)`

This means the score is the share of resolved challenges where the auditor's
claim still stood after review.

## Inputs

- `challenge_rejected_count`
  - resolved challenges that failed, which strengthens the auditor's record
- `challenge_upheld_count`
  - resolved challenges that succeeded, which weakens the auditor's record
- `resolved_challenge_count`
  - total resolved challenges used in the score
- `open_challenge_count`
  - tracked separately and excluded from the score until finalized
- `published_claim_count`
  - non-draft claims the auditor has taken responsibility for
- `draft_claim_count`
  - local claims that are still uncommitted

## Reputation Bands

- `provisional`
  - no resolved challenges yet
- `trusted`
  - score `>= 75`
- `mixed`
  - score `>= 40` and `< 75`
- `contested`
  - score `< 40`

The band is only a label. The raw counts remain the source of truth.

## Trust Assumptions

- deterministic and manual resolutions are treated the same once finalized
- unresolved disputes do not affect the score
- the score is descriptive, not a staking requirement or allowlist decision

## Gaming Risks

- low-volume auditors can look stronger or weaker than they really are
- repeated easy claims can inflate activity counts without proving judgment quality
- collusive challenge behavior is still possible unless the surrounding market
  treats challenge evidence seriously

Use the score alongside the raw counts, claim history, and validation trail.
