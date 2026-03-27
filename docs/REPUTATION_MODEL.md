# Auditor Reputation Model

Proof-of-Audit now separates two different signals that were previously collapsed
into one score:

- how challengeable an auditor's published claims are
- how often admissible challenges actually succeed against those claims

The API still returns a backward-compatible top-level `score` and `band`, but
those are now an aggregate over two component scores.

## Component Scores

### Challenge Openness Score

`challenge_openness_score` rewards auditors for publishing claims under broader
challenge conditions.

For each published claim, the API derives a per-claim policy openness score from
the normalized `challenge_policy`:

- evidence coverage: up to `35` points
- minimum severity threshold: up to `30` points
- allowing informational-only disagreements: `10` points
- not requiring material incorrectness: `10` points
- broad rather than strict admissibility: up to `15` points

The auditor's `challenge_openness_score` is the average of those per-claim
policy openness scores.

Interpretation:

- `open`
  - openness score `>= 75`
- `balanced`
  - openness score `>= 45` and `< 75`
- `restrictive`
  - openness score `< 45`
- `provisional`
  - no published claims yet

The API also returns `policy_openness_weight`, which is the openness score
normalized to the `0.00` to `1.00` range.

### Challenge Accuracy Score

`challenge_accuracy_score` measures how well claims hold up once a challenge is
actually admissible on the merits.

Rules:

- if there are no admissible resolved challenges, the score is neutral at `50`
- otherwise:

`challenge_accuracy_score = round(100 * admissible_challenge_rejected_count / admissible_resolved_challenge_count)`

Important:

- inadmissible challenges do **not** count as accuracy wins
- rejected inadmissible disputes are tracked separately in
  `inadmissible_challenge_count`
- only admissible resolved challenges feed the accuracy score

Interpretation:

- `strong`
  - accuracy score `>= 75`
- `mixed`
  - accuracy score `>= 40` and `< 75`
- `weak`
  - accuracy score `< 40`
- `provisional`
  - no admissible resolved challenges yet

## Aggregate Score

The API keeps the existing top-level `score` field for compatibility, but it is
now computed as:

`score = round(0.35 * challenge_openness_score + 0.65 * challenge_accuracy_score)`

This keeps challenge correctness as the dominant factor while still rewarding
auditors who publish under broader challenge conditions.

Aggregate bands:

- `trusted`
  - aggregate score `>= 75`
- `mixed`
  - aggregate score `>= 40` and `< 75`
- `contested`
  - aggregate score `< 40`
- `provisional`
  - no published claims and no admissible resolved challenges

## Inputs Returned By The API

The reputation payload now exposes:

- `challenge_openness_score`
- `challenge_openness_band`
- `challenge_accuracy_score`
- `challenge_accuracy_band`
- `policy_openness_weight`
- `admissible_resolved_challenge_count`
- `admissible_challenge_rejected_count`
- `admissible_challenge_upheld_count`
- `inadmissible_challenge_count`
- legacy aggregate `score`
- legacy aggregate `band`

The payload also publishes three formula strings:

- `challenge_openness_formula`
- `challenge_accuracy_formula`
- `formula`

## Trust Assumptions

- unresolved disputes do not affect accuracy
- inadmissible disputes affect neither openness nor accuracy retroactively; they
  are reported separately
- openness is derived from machine-readable policy metadata, not prose
- the aggregate score is descriptive, not a staking gate or allowlist decision

## Gaming Risks

- a broad policy can improve openness without proving judgment quality
- a very restrictive policy can preserve accuracy while reducing challengeability
- low-volume auditors can still look stronger or weaker than they really are
- collusive challenge behavior remains possible if the surrounding market does
  not treat evidence and admissibility seriously

Use the aggregate score only as a summary. The component scores and raw counts
are the more important operational signals.
