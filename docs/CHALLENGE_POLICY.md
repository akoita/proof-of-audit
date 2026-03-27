# Challenge Policy Grammar

`#212` adds a small verifier-checkable policy object that can be attached to a
published claim. The goal is not to encode arbitrary legal or moderation logic.
The goal is to let the API and verifier make a narrow admissibility decision
before a challenge can be treated as a valid dispute.

## Supported schema

Current policy version:

```json
{
  "policy_version": "challenge-policy/v1",
  "allowed_evidence_types": ["deterministic_fixture", "executable_test"],
  "min_severity_threshold": "info",
  "allow_informational_only": true,
  "requires_material_incorrectness": false,
  "admissibility_mode": "broad"
}
```

Supported fields:

- `allowed_evidence_types`
  - allowed values: `deterministic_fixture`, `executable_test`
  - challenges using any other evidence type are marked
    `inadmissible_evidence_type`
- `min_severity_threshold`
  - allowed values: `info`, `low`, `medium`, `high`, `critical`
  - `informational` is normalized to `info`
  - challenges below the threshold are marked
    `inadmissible_severity_below_threshold`
- `allow_informational_only`
  - when `false`, informational-only disagreements are inadmissible
- `requires_material_incorrectness`
  - when `true`, the verifier must support a materially incorrect claim outcome
  - current verifier-checkable signals are intentionally narrow:
    `comparison.status` must indicate `likely_new_issue` or
    `contradicts_audit_claim`
- `admissibility_mode`
  - `broad`: admit challenges even when the verifier cannot fully confirm them
  - `strict`: admit only verifier-confirmed challenges
  - non-confirmed strict-mode challenges are marked
    `inadmissible_policy_scope`

## Where the policy appears

The effective normalized policy is exposed in:

- `onchain.challenge_policy` on published audit records
- request-claim records returned by `GET /requests/{id}/claims`
- validation request claim metadata as `claim.challengePolicy`
- reputation claim metadata as `claim.challengePolicy`
- challenge verifier dossiers as `policy.effective_policy`

Challenge outcomes also include:

- `challenge.policy_admissibility_status`
- `challenge.policy_admissibility_rationale`
- `verification_dossier.policy.admissibility_status`

## Current scope

This grammar is intentionally limited to verifier-checkable inputs. It does not
support:

- free-form text clauses
- subjective reviewer instructions
- bespoke evidence rules outside the supported evidence types
- arbitrary boolean expressions over claim metadata
- on-chain enforcement of the full policy object

The settlement contract still enforces stake and request-claim eligibility. The
challenge policy is currently an API/verifier-side admissibility layer that runs
before automatic or manual resolution logic.
